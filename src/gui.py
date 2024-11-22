import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from bookcat import process_batch_file  # Import your batch file processing logic


class BatchFileProcessorApp:
    def __init__(self, master):
        """
        Initialize the GUI for batch file processing.
        """
        self.master = master
        self.master.title("Batch File Processor")

        # Instruction Label
        self.label = tk.Label(master, text="Select a batch file to process", font=("Arial", 12))
        self.label.pack(pady=10)

        # Process Button
        self.process_button = tk.Button(master, text="Process Batch File", command=self.on_process_button_click)
        self.process_button.pack(pady=10)

        # Status Label
        self.status_label = tk.Label(master, text="", font=("Arial", 10), fg="green")
        self.status_label.pack(pady=10)

    def on_process_button_click(self):
        """
        Callback for the "Process Batch File" button.
        """
        # Open a file dialog to select the batch file
        file_path = filedialog.askopenfilename(
            title="Select Batch File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not file_path:
            tk.messagebox.showinfo("Info", "No file selected. Operation cancelled.")
            return

        # Update status
        self.status_label.config(text="Processing...")

        # Start batch file processing
        try:
            process_batch_file(file_path)  # Pass the file path to your processing logic
            self.status_label.config(text="Processing complete!")
            tk.messagebox.showinfo("Success", "Processing complete! Check the output CSV.")
        except Exception as e:
            tk.messagebox.showerror("Error", f"An error occurred: {e}")
            self.status_label.config(text="Error occurred.")

