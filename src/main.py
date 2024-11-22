import tkinter as tk
from gui import BatchFileProcessorApp  # GUI implementation
from bookcat import main  # CLI functionality


if __name__ == "__main__":
    print("Choose the mode:")
    print("1. Command-line")
    print("2. GUI")
    mode = input("Enter 1 or 2: ").strip()

    if mode == "1":
        main()  # Run the CLI mode
    elif mode == "2":
        root = tk.Tk()
        app = BatchFileProcessorApp(root)  # Initialize the GUI application
        root.mainloop()  # Start the Tkinter main loop
    else:
        print("Invalid choice. Exiting.")

