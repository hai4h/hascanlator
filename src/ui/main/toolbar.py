from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QCheckBox, QLabel, QSizePolicy

class MainToolbar(QWidget):
    """The left-side vertical toolbar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Ensure it has a baseline but allow it to stretch horizontally to fit larger fonts naturally
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.setMinimumWidth(160)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.btn_load = QPushButton("Load")
        self.btn_reset = QPushButton("Reset")

        self.btn_peek = QPushButton("Peek")

        undo_redo_layout = QHBoxLayout()
        undo_redo_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_undo = QPushButton("Undo")
        self.btn_redo = QPushButton("Redo")
        undo_redo_layout.addWidget(self.btn_undo)
        undo_redo_layout.addWidget(self.btn_redo)

        from PySide6.QtWidgets import QToolButton
        auto_scan_layout = QHBoxLayout()
        auto_scan_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_auto_process = QCheckBox("Auto-Scan")
        self.btn_auto_scan_config = QToolButton()
        self.btn_auto_scan_config.setText("⚙")
        self.btn_auto_scan_config.setToolTip("Configure Auto-Scan Pipeline")
        self.btn_auto_scan_config.setPopupMode(QToolButton.InstantPopup)
        auto_scan_layout.addWidget(self.chk_auto_process)
        auto_scan_layout.addWidget(self.btn_auto_scan_config)

        self.btn_auto_detect = QPushButton("Auto Detect")
        self.btn_add_box = QPushButton("Add Box (Manual)")
        self.btn_settings = QPushButton("Settings")

        layout.addWidget(self.btn_load)
        layout.addWidget(self.btn_reset)
        layout.addWidget(self.btn_peek)
        layout.addLayout(undo_redo_layout)
        layout.addWidget(QLabel("<hr>"))
        layout.addLayout(auto_scan_layout)
        layout.addWidget(self.btn_auto_detect)
        layout.addWidget(self.btn_add_box)
        layout.addStretch()
        layout.addWidget(self.btn_settings)
