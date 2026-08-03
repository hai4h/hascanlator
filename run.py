import sys
import os
os.environ["QT_LOGGING_RULES"] = "qt.qpa.wayland.textinput.warning=false"

# Suppress extra YOLO terminal output
os.environ["YOLO_VERBOSE"] = "False"

from PySide6.QtWidgets import QApplication
from src.ui.main.window import HAScanlatorWindow

def main():
    try:
        import jurigged
        jurigged.watch(pattern="./src")
    except ImportError:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = HAScanlatorWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
