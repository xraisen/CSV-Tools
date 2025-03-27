import os
import math
import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import threading

# CSV Splitter class remains unchanged
class CSVSplitter:
    """
    Uses pandas to load the CSV and provides methods to split
    by number of rows or by file size (in MB).
    """
    def __init__(self, input_file):
        """Initialize with input file path."""
        self.input_file = input_file
        
        try:
            self.df = pd.read_csv(input_file)
        except Exception as e:
            raise ValueError(f"Failed to read CSV: {e}")
        
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """Assign a function to call for progress updates."""
        self.progress_callback = callback
    
    def get_file_size(self, file_path):
        """Returns the file size in MB."""
        return os.path.getsize(file_path) / (1024 * 1024)
    
    def get_output_dir(self):
        """
        Generate output directory name based on the input file name + timestamp.
        Example: mydata_20250321_153045
        """
        base_name = os.path.splitext(os.path.basename(self.input_file))[0]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{base_name}_{timestamp}"
    
    def split_by_rows(self, output_dir, rows_per_file=50000):
        """Split CSV by number of rows per file."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        total_rows = len(self.df)
        num_files = math.ceil(total_rows / rows_per_file)
        base_name = os.path.splitext(os.path.basename(self.input_file))[0]
        
        for i in range(num_files):
            if self.progress_callback:
                progress = ((i + 1) / num_files) * 100
                self.progress_callback(progress)
            
            start_idx = i * rows_per_file
            end_idx = min((i + 1) * rows_per_file, total_rows)
            
            output_file = os.path.join(output_dir, f'{base_name}_part_{i + 1}.csv')
            self.df[start_idx:end_idx].to_csv(output_file, index=False)
        
        return num_files
    
    def split_by_size(self, output_dir, max_size_mb=50):
        """
        Split CSV by file size (in MB).
        Estimates rows_per_file based on total size and rows.
        """
        file_size_bytes = os.path.getsize(self.input_file)
        if file_size_bytes == 0:
            raise ValueError("Input file size is zero; cannot split.")
        
        total_rows = len(self.df)
        rows_per_mb = total_rows / (file_size_bytes / (1024 * 1024))
        rows_per_file = int(rows_per_mb * max_size_mb)
        
        return self.split_by_rows(output_dir, rows_per_file)

class SplitterGUI:
    """
    A Tkinter-based GUI for CSV Splitting with modern styling,
    progress bar, and options to split by rows or size.
    """
    def __init__(self, root):
        self.root = root
        self.root.title('CSV File Splitter')
        
        # Set window size and background
        self.root.geometry("1000x700")
        self.root.configure(bg='#f5f7fa')
        self.root.minsize(800, 600)
        
        # Make the window responsive
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Apply TTK styling
        self.setup_styles()
        self.create_widgets()
    
    def setup_styles(self):
        """Configure TTK styles for the GUI."""
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure('TFrame', background='#f5f7fa')
        style.configure('TLabel', background='#f5f7fa', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=5)
        
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'))
        style.configure('Info.TLabel', font=('Segoe UI', 9), foreground='#666666')
        style.configure('Success.TLabel', font=('Segoe UI', 10), foreground='#28a745')
        style.configure('Footer.TLabel', font=('Segoe UI', 9, 'italic'), foreground='#666666')
        
        style.configure('Custom.TLabelframe', background='#f5f7fa', borderwidth=1, relief='solid')
        style.configure('Custom.TLabelframe.Label', font=('Segoe UI', 11, 'bold'), foreground='#333')
        
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#ddd",
            background="#4a90e2",
            thickness=15
        )
        
        style.map(
            'TButton',
            background=[('active', '#4a90e2')],
            foreground=[('active', 'white')]
        )
    
    def create_widgets(self):
        """Create and arrange all GUI widgets."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding='30 30 30 30')
        main_frame.grid(row=0, column=0, sticky='nsew')
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Header
        header_label = ttk.Label(
            main_frame, 
            text='CSV File Splitter - Split large CSV files easily',
            style='Header.TLabel'
        )
        header_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky='w')
        
        # File selection area
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(0, 10))
        file_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(file_frame, text='Input CSV File:', style='TLabel').grid(row=0, column=0, sticky='w', padx=(0, 5))
        self.file_entry = ttk.Entry(file_frame, width=60)
        self.file_entry.grid(row=0, column=1, padx=5, sticky='ew')
        browse_btn = ttk.Button(file_frame, text='Browse', command=self.browse_file)
        browse_btn.grid(row=0, column=2, padx=5)
        
        ttk.Label(
            file_frame, 
            text='Select the CSV file you want to split into smaller files',
            style='Info.TLabel'
        ).grid(row=1, column=0, columnspan=3, sticky='w', pady=(2, 0))
        
        # Options for splitting
        option_frame = ttk.Labelframe(
            main_frame, 
            text='Split Options', 
            padding='15 15 15 15', 
            style='Custom.TLabelframe'
        )
        option_frame.grid(row=2, column=0, columnspan=3, pady=20, sticky='ew')
        
        self.split_method = tk.StringVar(value='rows')
        ttk.Radiobutton(option_frame, text='Split by Rows', value='rows', variable=self.split_method).grid(row=0, column=0, padx=10, pady=5)
        ttk.Radiobutton(option_frame, text='Split by Size (MB)', value='size', variable=self.split_method).grid(row=0, column=1, padx=10, pady=5)
        
        ttk.Label(
            option_frame, 
            text='Choose to split by number of rows or by file size in megabytes',
            style='Info.TLabel'
        ).grid(row=1, column=0, columnspan=2, sticky='w', pady=(5, 10))
        
        value_frame = ttk.Frame(option_frame)
        value_frame.grid(row=2, column=0, columnspan=2, sticky='w')
        
        ttk.Label(value_frame, text='Value:', style='TLabel').grid(row=0, column=0, padx=(0, 5))
        self.value_entry = ttk.Entry(value_frame, width=15)
        self.value_entry.grid(row=0, column=1, padx=(0, 5))
        self.value_entry.insert(0, '50000')
        
        ttk.Label(
            value_frame, 
            text='(rows or MB depending on split method)',
            style='Info.TLabel'
        ).grid(row=0, column=2, padx=(5, 0))
        
        # Output info
        output_frame = ttk.Labelframe(
            main_frame, 
            text='Output Information', 
            padding='15 15 15 15', 
            style='Custom.TLabelframe'
        )
        output_frame.grid(row=3, column=0, columnspan=3, pady=20, sticky='ew')
        
        ttk.Label(
            output_frame, 
            text='Output files will be created in a new folder next to your input file:',
            style='Info.TLabel'
        ).grid(row=0, column=0, sticky='w', pady=(0, 5))
        
        ttk.Label(
            output_frame, 
            text='Format: [input_filename]_[timestamp] - [Row/Filesize]/[input_filename]_part_1.csv etc.',
            style='Info.TLabel'
        ).grid(row=1, column=0, sticky='w')
        
        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(
            main_frame, 
            length=500, 
            mode='determinate',
            variable=self.progress_var,
            style="Custom.Horizontal.TProgressbar"
        )
        self.progress.grid(row=4, column=0, columnspan=3, pady=20, sticky='ew')
        
        # Status label
        self.status_label = ttk.Label(main_frame, text='', style='Success.TLabel')
        self.status_label.grid(row=5, column=0, columnspan=3, pady=10)
        
        # Split button
        self.split_button = ttk.Button(main_frame, text='Split CSV', command=self.start_split)
        self.split_button.grid(row=6, column=0, columnspan=3, pady=20)
        
        # Footer with author and owner info
        footer_label = ttk.Label(
            main_frame,
            text='Created by Jose Espinosa from AE1O1, owned by Ahmed Elhadi\njpm.onestop@gmail.com | © 2025',
            style='Footer.TLabel'
        )
        footer_label.grid(row=7, column=0, columnspan=3, pady=(20, 0), sticky='s')
    
    def browse_file(self):
        """Open file dialog to select a CSV file."""
        filename = filedialog.askopenfilename(filetypes=[('CSV files', '*.csv'), ('All files', '*.*')])
        if filename:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)
    
    def update_progress(self, value):
        """Update the progress bar (0-100)."""
        self.progress_var.set(value)
        if value >= 100:
            self.status_label.config(text='Splitting complete! Output folder has been created.')
            self.split_button.config(state='normal')
        else:
            self.status_label.config(text=f'Splitting in progress... {value:.2f}%')
    
    def start_split(self):
        """Validate input and start the splitting process in a separate thread."""
        input_file = self.file_entry.get().strip()
        if not input_file:
            messagebox.showerror('Error', 'Please select an input file')
            return
        
        try:
            splitter = CSVSplitter(input_file)
            splitter.set_progress_callback(self.update_progress)
            
            output_dir_base = splitter.get_output_dir()
            
            if self.split_method.get() == 'rows':
                suffix = 'Row'
                value = int(self.value_entry.get() or 50000)
            else:
                suffix = 'Filesize'
                value = float(self.value_entry.get() or 50)
            
            output_dir = os.path.join(
                os.path.dirname(input_file),
                f"{output_dir_base} - {suffix}"
            )
            
            self.split_button.config(state='disabled')
            self.status_label.config(text='Splitting in progress...')
            self.progress_var.set(0)
            
            def split_thread():
                try:
                    if self.split_method.get() == 'rows':
                        splitter.split_by_rows(output_dir, rows_per_file=value)
                    else:
                        splitter.split_by_size(output_dir, max_size_mb=value)
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror('Error', str(e)))
                finally:
                    self.root.after(0, lambda: self.split_button.config(state='normal'))
            
            threading.Thread(target=split_thread, daemon=True).start()
        
        except Exception as e:
            messagebox.showerror('Error', str(e))
            self.split_button.config(state='normal')

def main():
    root = tk.Tk()
    app = SplitterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()