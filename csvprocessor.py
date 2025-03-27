import csv
import os
import re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import logging

# Set up logging with detailed formatting
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# ------------------------------
# Core CSV Processing Logic
# ------------------------------

def split_values(raw_text, split_mode):
    """
    Splits the provided raw_text into a list based on the split_mode.
    
    Args:
        raw_text (str): The input text to split.
        split_mode (str): The split mode ("Comma" or "Rows").
    
    Returns:
        list: A list of split values.
    """
    raw_text = raw_text.strip()
    if not raw_text:
        return []
    if split_mode == "Comma":
        return [val.strip() for val in raw_text.split(",") if val.strip()]
    elif split_mode == "Rows":
        return [val.strip() for val in raw_text.splitlines() if val.strip()]
    return [raw_text]

def collect_emails_and_phones(row, headers):
    """
    Extracts emails and phone numbers from a CSV row.
    
    Args:
        row (dict): A CSV row.
        headers (list): List of CSV header names.
    
    Returns:
        tuple: Two lists, one for emails and one for phone numbers.
    """
    emails = []
    phones = []
    
    # Collect all email and phone columns
    for header in headers:
        header_lower = header.lower()
        if "email" in header_lower:
            email_val = row.get(header, "").strip()
            if email_val:
                emails.append(email_val)
        elif "phone" in header_lower:
            phone_val = row.get(header, "").strip()
            if phone_val:
                phones.append(phone_val)
    
    return list(dict.fromkeys(emails)), list(dict.fromkeys(phones))

def consolidate_rows(reader, key_fields):
    """
    Consolidates rows from the CSV that share the same key fields.
    
    Args:
        reader (csv.DictReader): CSV reader object.
        key_fields (list): List of field names used as keys for consolidation.
    
    Returns:
        dict: Consolidated data with keys mapping to a dictionary containing emails, phones, and base data.
    """
    consolidated = {}
    row_count = 0
    for row in reader:
        row_count += 1
        key = tuple(row.get(field, "").strip() for field in key_fields)
        if key not in consolidated:
            consolidated[key] = {"emails": [], "phones": [], "base": {}}
        entry = consolidated[key]
        emails, phones = collect_emails_and_phones(row, reader.fieldnames)
        entry["emails"].extend(emails)
        entry["phones"].extend(phones)
        for field in reader.fieldnames:
            if field not in entry["base"] or not entry["base"][field]:
                entry["base"][field] = row.get(field, "").strip()
        entry["emails"] = list(dict.fromkeys(entry["emails"]))
        entry["phones"] = list(dict.fromkeys(entry["phones"]))
    logging.debug(f"Processed {row_count} rows, consolidated into {len(consolidated)} unique records")
    return consolidated

def process_csv_custom(input_file, output_definitions, streamline_type, split_mode):
    """
    Processes the input CSV file, consolidates rows, and outputs a new CSV based on selected output definitions,
    streamline type, and split mode.
    
    Args:
        input_file (str): Path to the input CSV file.
        output_definitions (list): List of CSV columns to include in the output.
        streamline_type (str): How emails/phones are handled ("None", "Email", "Phone", "Email & Phone").
        split_mode (str): How data is output ("Comma" or "Rows").
    
    Returns:
        str or None: The path to the output file if successful, else None.
    """
    try:
        logging.info(f"Starting processing of {input_file}")
        with open(input_file, newline='', encoding='utf-8-sig') as csv_in:
            sample = csv_in.read(1024)
            csv_in.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(csv_in, dialect=dialect)
            headers = reader.fieldnames or []
            if not headers:
                logging.error("No headers found in CSV")
                return None

            # Use first few columns as key fields if standard fields not found
            key_fields = ["ACTIVATION", "Phone1", "Phone2", "Email1"]
            key_fields = [f for f in key_fields if f in headers] or headers[:4]
            logging.debug(f"Using key fields for consolidation: {key_fields}")
            consolidated_data = consolidate_rows(reader, key_fields)

            # Prepare output headers
            out_headers = list(output_definitions)
            if streamline_type in ("Email", "Email & Phone"):
                out_headers.append("Email")
            if streamline_type in ("Phone", "Email & Phone"):
                out_headers.append("Phone")
            logging.debug(f"Output headers: {out_headers}")

            base, ext = os.path.splitext(input_file)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"{base}_processed_{timestamp}{ext}"

            with open(output_file, 'w', newline='', encoding='utf-8') as csv_out:
                writer = csv.DictWriter(csv_out, fieldnames=out_headers)
                writer.writeheader()

                for key, data in consolidated_data.items():
                    base_row = {hdr: data["base"].get(hdr, "") for hdr in output_definitions if hdr in data["base"]}
                    valid_emails = [e for e in data["emails"] if "@" in e]
                    phones = data["phones"]
                    phone_str = ", ".join(phones) if phones else ""
                    email_str = ", ".join(valid_emails) if valid_emails else ""

                    if streamline_type == "Email & Phone":
                        if split_mode == "Comma":
                            out_row = dict(base_row)
                            if "Email" in out_headers:
                                out_row["Email"] = email_str
                            if "Phone" in out_headers:
                                out_row["Phone"] = phone_str
                            writer.writerow(out_row)
                        elif split_mode == "Rows":
                            if not valid_emails and not phones:
                                continue  # Skip if no data
                            max_count = max(len(valid_emails), len(phones)) or 1
                            for i in range(max_count):
                                out_row = dict(base_row)
                                if "Email" in out_headers:
                                    out_row["Email"] = valid_emails[i] if i < len(valid_emails) else ""
                                if "Phone" in out_headers:
                                    out_row["Phone"] = phones[i] if i < len(phones) else ""
                                writer.writerow(out_row)
                    elif streamline_type == "Email":
                        if split_mode == "Comma":
                            if not valid_emails:  # Skip if no emails
                                continue
                            out_row = dict(base_row)
                            if "Email" in out_headers:
                                out_row["Email"] = email_str
                            writer.writerow(out_row)
                        elif split_mode == "Rows":
                            if not valid_emails:  # Skip if no emails
                                continue
                            for email in valid_emails:
                                out_row = dict(base_row)
                                out_row["Email"] = email
                                writer.writerow(out_row)
                    elif streamline_type == "Phone":
                        if split_mode == "Comma":
                            if not phones:  # Skip if no phones
                                continue
                            out_row = dict(base_row)
                            if "Phone" in out_headers:
                                out_row["Phone"] = phone_str
                            writer.writerow(out_row)
                        elif split_mode == "Rows":
                            if not phones:  # Skip if no phones
                                continue
                            for phone in phones:
                                out_row = dict(base_row)
                                out_row["Phone"] = phone
                                writer.writerow(out_row)
                    else:  # "None"
                        if split_mode == "Comma":
                            out_row = dict(base_row)
                            if "Email" in out_headers:
                                out_row["Email"] = email_str
                            if "Phone" in out_headers:
                                out_row["Phone"] = phone_str
                            writer.writerow(out_row)
                        elif split_mode == "Rows":
                            if not valid_emails and not phones:
                                continue  # Skip if no data
                            max_count = max(len(valid_emails), len(phones)) or 1
                            for i in range(max_count):
                                out_row = dict(base_row)
                                if "Email" in out_headers:
                                    out_row["Email"] = valid_emails[i] if i < len(valid_emails) else ""
                                if "Phone" in out_headers:
                                    out_row["Phone"] = phones[i] if i < len(phones) else ""
                                writer.writerow(out_row)

            logging.info(f"Processing complete. Output file: {output_file}")
            return output_file

    except Exception as e:
        logging.error(f"Error processing CSV: {e}", exc_info=True)
        return None

# ------------------------------
# Modal Dialog for Column Selection
# ------------------------------

class SelectColumnsDialog(tk.Toplevel):
    """
    Modal dialog that allows the user to select which columns to include in the output CSV.
    Pressing the Enter key triggers the OK button.
    """
    def __init__(self, master, available_headers):
        super().__init__(master)
        self.title("Select Columns")
        self.geometry("400x500")
        self.transient(master)
        self.grab_set()

        self.available_headers = available_headers
        self.output_definitions = None

        instruction = (
            "Select the columns you wish to include in the output.\n"
            "Check the boxes for each header you want to retain.\n"
            "Then click OK (or press Enter) to confirm your selection."
        )
        ttk.Label(self, text=instruction, wraplength=380, justify="left").pack(pady=10, padx=10)

        canvas = tk.Canvas(self, borderwidth=0, height=300)
        frame = ttk.Frame(canvas)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda event, canvas=canvas: canvas.configure(scrollregion=canvas.bbox("all")))

        self.header_vars = {}
        for header in available_headers:
            var = tk.BooleanVar(value=False)
            self.header_vars[header] = var
            row_frame = ttk.Frame(frame)
            row_frame.pack(fill="x", pady=2, padx=5)
            chk = ttk.Checkbutton(row_frame, variable=var, text=header)
            chk.pack(side="left", anchor="w")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ok_btn = ttk.Button(btn_frame, text="OK", command=self.on_ok)
        ok_btn.pack(side="left", padx=5)
        self.bind("<Return>", lambda event: self.on_ok())

    def on_ok(self):
        definitions = [header for header, var in self.header_vars.items() if var.get()]
        if not definitions:
            messagebox.showerror("Error", "Please select at least one column.")
            return
        self.output_definitions = definitions
        self.destroy()

# ------------------------------
# Main GUI
# ------------------------------

class CSVProcessorGUI:
    """
    Main graphical user interface for the CSV Processor.
    Allows file selection, column selection, and choosing how to process and output the CSV.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("CSV Processor (Enhanced)")
        self.root.geometry("800x650")
        self.root.configure(bg="#f5f5f5")
        self.output_definitions = None
        self.available_headers = None

        self.streamline_var = tk.StringVar(value="None")
        streamline_options = ["None", "Email", "Phone", "Email & Phone"]
        self.split_var = tk.StringVar(value="Comma")
        split_options = ["Comma", "Rows"]

        description = (
            "How-To:\n"
            "- Browse and select your CSV file.\n"
            "- Click 'Select Columns' to choose output headers.\n"
            "- Choose a streamline type:\n"
            "    * 'None':\n"
            "       - 'Comma': One row with all emails and phones comma-separated.\n"
            "       - 'Rows': One row per email-phone pair, max count if uneven; skips if no data.\n"
            "    * 'Email':\n"
            "       - 'Comma': One row with all emails comma-separated; skips if no emails.\n"
            "       - 'Rows': One row per email; skips if no emails.\n"
            "    * 'Phone':\n"
            "       - 'Comma': One row with all phones comma-separated; skips if no phones.\n"
            "       - 'Rows': One row per phone; skips if no phones.\n"
            "    * 'Email & Phone':\n"
            "       - 'Comma': One row with all emails and phones comma-separated.\n"
            "       - 'Rows': One row per email-phone pair, blank if uneven; skips if no data.\n"
            "- Note: Email/Phone columns are automatically added based on streamline type."
        )
        desc_label = ttk.Label(root, text=description, wraplength=780, justify="left", font=("Segoe UI", 10))
        desc_label.pack(pady=(10, 5), padx=10, anchor="w")

        self.main_frame = ttk.Frame(root, padding=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.header_label = ttk.Label(self.main_frame, text="CSV Processor (Enhanced)", font=("Segoe UI", 14, "bold"))
        self.header_label.grid(row=0, column=0, columnspan=4, sticky="W", pady=(0, 10))
        
        ttk.Label(self.main_frame, text="Select CSV File:").grid(row=1, column=0, sticky="W", padx=(0, 5))
        self.file_entry = ttk.Entry(self.main_frame, width=50)
        self.file_entry.grid(row=1, column=1, sticky="EW")
        self.file_entry.insert(0, "Enter or browse for CSV file path here")
        self.browse_button = ttk.Button(self.main_frame, text="Browse", command=self.browse_file)
        self.browse_button.grid(row=1, column=2, padx=5, sticky="W")
        ttk.Label(self.main_frame, text="(Click 'Browse' to select a file)").grid(row=1, column=3, sticky="W")
        
        self.columns_button = ttk.Button(self.main_frame, text="Select Columns", command=self.select_columns)
        self.columns_button.grid(row=2, column=1, pady=(15, 0), sticky="W")
        ttk.Label(self.main_frame, text="(Select which CSV headers to output)").grid(row=2, column=2, sticky="W")
        
        ttk.Label(self.main_frame, text="Streamline Type:").grid(row=3, column=0, sticky="W", padx=(0, 5), pady=(15, 0))
        self.streamline_combo = ttk.Combobox(self.main_frame, textvariable=self.streamline_var,
                                             values=streamline_options, state="readonly", width=15)
        self.streamline_combo.grid(row=3, column=1, sticky="W", padx=(0, 5), pady=(15, 0))
        ttk.Label(self.main_frame, text="(Defines how emails/phones are handled)").grid(row=3, column=2, sticky="W", pady=(15, 0))
        
        ttk.Label(self.main_frame, text="Split Mode:").grid(row=4, column=0, sticky="W", padx=(0, 5), pady=(10, 0))
        self.split_combo = ttk.Combobox(self.main_frame, textvariable=self.split_var,
                                        values=split_options, state="readonly", width=15)
        self.split_combo.grid(row=4, column=1, sticky="W", padx=(0, 5), pady=(10, 0))
        ttk.Label(self.main_frame, text="(Defines output format)").grid(row=4, column=2, sticky="W", pady=(10, 0))
        
        self.process_button = ttk.Button(self.main_frame, text="Process CSV", command=self.start_processing)
        self.process_button.grid(row=5, column=1, pady=(25, 0), sticky="W")
        ttk.Label(self.main_frame, text="(Click to start processing)").grid(row=5, column=2, sticky="W", pady=(25, 0))
        
        self.status_label = ttk.Label(self.main_frame, text="", foreground="#28a745")
        self.status_label.grid(row=6, column=0, columnspan=4, sticky="W", pady=(15, 0))
        
        footer = ttk.Label(root, text="Created by Jose Espinosa from AE1O1 owned by Ahmed Elhadi – jpm.onestop@gmail.com",
                           font=("Segoe UI", 8), foreground="gray")
        footer.pack(side="bottom", pady=5)
        
        self.main_frame.columnconfigure(1, weight=1)

    def browse_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if file_path:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, file_path)
            try:
                with open(file_path, newline='', encoding='utf-8-sig') as csv_in:
                    sample = csv_in.read(1024)
                    csv_in.seek(0)
                    try:
                        dialect = csv.Sniffer().sniff(sample)
                    except csv.Error:
                        dialect = csv.excel
                    reader = csv.DictReader(csv_in, dialect=dialect)
                    self.available_headers = reader.fieldnames
                    logging.debug(f"Loaded headers from {file_path}: {self.available_headers}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read file headers: {e}")
                self.available_headers = []

    def select_columns(self):
        if not self.available_headers:
            messagebox.showerror("Error", "Please select a CSV file first to load available headers.")
            return
        dialog = SelectColumnsDialog(self.root, self.available_headers)
        self.root.wait_window(dialog)
        if dialog.output_definitions:
            self.output_definitions = dialog.output_definitions
            defs_text = ", ".join(self.output_definitions)
            self.status_label.config(text="Selected columns: " + defs_text)
            logging.debug(f"Selected columns: {self.output_definitions}")
        else:
            self.status_label.config(text="No columns selected.")

    def start_processing(self):
        input_file = self.file_entry.get().strip()
        if not input_file:
            messagebox.showerror("Error", "Please select a CSV file.")
            return
        if not self.output_definitions:
            messagebox.showerror("Error", "Please select columns to output before processing.")
            return

        streamline_type = self.streamline_var.get()
        split_mode = self.split_combo.get()

        self.process_button.config(state="disabled")
        self.status_label.config(text="Processing...")

        def run_process():
            try:
                output_file = process_csv_custom(input_file, self.output_definitions, streamline_type, split_mode)
                msg = f"CSV processing completed!\nOutput file: {output_file}" if output_file else "No output file generated."
            except Exception as e:
                logging.error(f"Thread exception: {e}", exc_info=True)
                msg = f"Error during processing: {str(e)}"
            self.root.after(0, lambda: self.update_status(msg))

        thread = threading.Thread(target=run_process, daemon=True)
        thread.start()

        def check_thread():
            if thread.is_alive():
                logging.warning("Processing taking too long, forcing stop.")
                self.update_status("Processing timed out after 60 seconds.")
            else:
                logging.debug("Thread completed within timeout.")
        self.root.after(60000, check_thread)

    def update_status(self, msg):
        self.status_label.config(text=msg)
        self.process_button.config(state="normal")
        logging.info(f"Status updated: {msg}")

def main():
    root = tk.Tk()
    app = CSVProcessorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()