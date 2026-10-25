# main.py
import logging
import tkinter as tk
from extraction_gui import ExtractionGUI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    root = tk.Tk()
    app = ExtractionGUI(root)
    root.mainloop()