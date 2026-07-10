from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Qt

class TypesetToolBar(QWidget):
    """Contextual vertical toolbar that appears next to the canvas for formatting."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(50)
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-left: 1px solid #3c3c3c;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(10)

        def create_btn(icon_text, tooltip):
            btn = QPushButton(icon_text)
            btn.setToolTip(tooltip)
            btn.setFixedSize(38, 38)
            btn.setStyleSheet("""
                QPushButton { 
                    font-size: 16px; 
                    font-weight: bold; 
                    border-radius: 4px;
                }
            """)
            layout.addWidget(btn)
            return btn

        self.btn_clean_bubble = create_btn("⌫", "Smart Clean Bubble (Erase text)")
        self.btn_toggle_typeset = create_btn("⊙", "Toggle Typeset Visibility")
        
        layout.addSpacing(10)
        
        self.btn_align_left = create_btn("|<", "Align Left")
        self.btn_align_center = create_btn("≡", "Align Center")
        self.btn_align_right = create_btn(">|", "Align Right")
        
        layout.addSpacing(10)
        
        self.btn_valign_top = create_btn("⇡", "Align Top")
        self.btn_valign_middle = create_btn("⇕", "Align Middle")
        self.btn_valign_bottom = create_btn("⇣", "Align Bottom")
        
        layout.addSpacing(10)
        
        self.btn_indent_minus = create_btn("-", "Decrease Indent")
        self.btn_indent_plus = create_btn("+", "Increase Indent")
        
        layout.addStretch()