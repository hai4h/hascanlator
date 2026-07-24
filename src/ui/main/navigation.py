from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSpinBox, QLabel
from PySide6.QtCore import Qt, Signal

class BottomNavigation(QWidget):
    page_jump_requested = Signal(int)
    """The bottom bar for flipping between manga pages."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)

        self.btn_prev = QPushButton("< Previous Page")

        # Center Container for cleanly separated labels and input
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)
        center_layout.setAlignment(Qt.AlignCenter)

        lbl_prefix = QLabel("Page")
        lbl_prefix.setStyleSheet("color: #ccc; font-size: 14px;")

        self.spin_page = QSpinBox()
        self.spin_page.setAlignment(Qt.AlignCenter)
        self.spin_page.setButtonSymbols(QSpinBox.NoButtons)
        self.spin_page.setRange(0, 0)
        self.spin_page.setStyleSheet("""
            QSpinBox { font-size: 14px; padding: 4px; border: 1px solid #555; background-color: #333; color: white; border-radius: 4px; min-width: 40px; }
            QSpinBox:disabled { background-color: #2b2b2b; color: #777; }
        """)

        # When user finishes typing and hits Enter
        self.spin_page.editingFinished.connect(self._on_jump_triggered)

        self.lbl_total = QLabel(" / 0")
        self.lbl_total.setStyleSheet("color: #ccc; font-size: 14px;")

        center_layout.addWidget(lbl_prefix)
        center_layout.addWidget(self.spin_page)
        center_layout.addWidget(self.lbl_total)

        self.btn_next = QPushButton("Next Page >")

        layout.addWidget(self.btn_prev)
        layout.addWidget(center_widget, stretch=1)
        layout.addWidget(self.btn_next)

        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.spin_page.setEnabled(False)

    def _on_jump_triggered(self):
        self.page_jump_requested.emit(self.spin_page.value() - 1)

    def update_labels(self, current, total):
        self.spin_page.blockSignals(True)
        if total > 0:
            self.spin_page.setRange(1, total)
            self.spin_page.setValue(current)
            self.lbl_total.setText(f" / {total}")
            self.spin_page.setEnabled(True)
        else:
            self.spin_page.setRange(0, 0)
            self.spin_page.setValue(0)
            self.lbl_total.setText(" / 0")
            self.spin_page.setEnabled(False)
        self.spin_page.blockSignals(False)
