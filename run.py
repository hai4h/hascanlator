import sys
import os

# Suppress extra YOLO terminal output
os.environ["YOLO_VERBOSE"] = "False"

from PySide6.QtWidgets import QApplication
from src.ui.main.window import HAScanlatorWindow

def main():
    try:
        import jurigged
        jurigged.watch()
    except ImportError:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = HAScanlatorWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
