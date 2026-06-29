from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt

class BottomNavigation(QWidget):
    """The bottom bar for flipping between manga pages."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        
        self.btn_prev = QPushButton("< Previous Page")
        self.lbl_page = QLabel("0 / 0")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.btn_next = QPushButton("Next Page >")
        
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.lbl_page, stretch=1)
        layout.addWidget(self.btn_next)
        
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        
    def update_labels(self, current, total):
        self.lbl_page.setText(f"Page {current} of {total}")