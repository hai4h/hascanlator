import sys
import os

# Suppress extra YOLO terminal output
os.environ["YOLO_VERBOSE"] = "False"

from PySide6.QtWidgets import QApplication
from src.ui.main_window import HAScanlatorWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = HAScanlatorWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()