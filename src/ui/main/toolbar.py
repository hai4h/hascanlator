from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QCheckBox, QLabel

class MainToolbar(QWidget):
    """The left-side vertical toolbar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(160)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.btn_load = QPushButton("Load")
        self.btn_reset = QPushButton("Reset")

        self.btn_peek = QPushButton("Peek")
        self.btn_undo = QPushButton("Undo")

        self.chk_auto_process = QCheckBox("Auto-Scan")

        self.btn_auto_detect = QPushButton("Auto Detect")
        self.btn_add_box = QPushButton("Add Box (Manual)")
        self.btn_settings = QPushButton("Settings")

        layout.addWidget(self.btn_load)
        layout.addWidget(self.btn_reset)
        layout.addWidget(self.btn_peek)
        layout.addWidget(self.btn_undo)
        layout.addWidget(QLabel("<hr>"))
        layout.addWidget(self.chk_auto_process)
        layout.addWidget(self.btn_auto_detect)
        layout.addWidget(self.btn_add_box)
        layout.addStretch()
        layout.addWidget(self.btn_settings)
