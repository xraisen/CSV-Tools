import tkinter as tk
from tkinter import ttk

# Create the main window
root = tk.Tk()
root.title("Treeview Example")
root.geometry("400x300")

# Create a Treeview widget
tree = ttk.Treeview(root, columns=("Size", "Type"), show="headings", height=10)

# Define column headings
tree.heading("Size", text="Size (KB)")
tree.heading("Type", text="Type")

# Configure column widths
tree.column("Size", width=100, anchor="center")
tree.column("Type", width=100, anchor="center")

# Add some sample data
# Insert a parent node (e.g., a folder)
parent = tree.insert("", "end", text="Documents", values=("N/A", "Folder"))

# Insert child nodes (e.g., files inside the folder)
tree.insert(parent, "end", text="Report.pdf", values=("150", "File"))
tree.insert(parent, "end", text="Notes.txt", values=("5", "File"))

# Insert another parent node
parent2 = tree.insert("", "end", text="Pictures", values=("N/A", "Folder"))
tree.insert(parent2, "end", text="Vacation.jpg", values=("300", "File"))

# Pack the Treeview widget into the window
tree.pack(pady=20)

# Function to handle item selection (optional)
def on_select(event):
    selected_item = tree.selection()  # Get selected item
    if selected_item:
        item = tree.item(selected_item)
        print(f"Selected: {item['text']} - Size: {item['values'][0]}, Type: {item['values'][1]}")

# Bind the selection event
tree.bind("<<TreeviewSelect>>", on_select)

# Start the main event loop
root.mainloop()