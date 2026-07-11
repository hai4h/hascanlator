from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMenu, 
    QWidgetAction, QGridLayout, QToolButton, QLabel
)
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
            QPushButton::menu-indicator { 
                image: none; 
                width: 0px;
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
            
        def create_reset_btn(text):
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton { 
                    font-size: 12px; 
                    border-radius: 4px; 
                    background: #3a3a3a; 
                    color: #d9534f; 
                    border: 1px solid #555555; 
                    padding: 4px; 
                } 
                QPushButton:hover { background: #555555; color: white; }
                QPushButton:pressed { background: #222222; }
            """)
            return btn

        # --- Basic Tools ---
        self.btn_clean_bubble = create_btn("⌫", "Smart Clean Bubble (Erase text)")
        self.btn_toggle_typeset = create_btn("⊙", "Toggle Typeset Visibility")
        
        layout.addSpacing(10)
        
        # --- Compact Alignment Menu ---
        self.btn_align = create_btn("≡", "Text Alignment")
        self.align_menu = QMenu(self)
        self.align_menu.setStyleSheet("border: none;")
        
        align_widget = QWidget()
        align_widget.setStyleSheet("QWidget { background-color: #333333; border: 1px solid #555555; }")
        align_layout = QGridLayout(align_widget)
        align_layout.setContentsMargins(6, 6, 6, 6)
        align_layout.setSpacing(6)

        def create_menu_btn(icon_text, tooltip):
            btn = QToolButton()
            btn.setText(icon_text)
            btn.setToolTip(tooltip)
            btn.setFixedSize(34, 34)
            btn.setStyleSheet("""
                QToolButton { font-size: 16px; font-weight: bold; border-radius: 4px; background: transparent; color: white; border: none; } 
                QToolButton:hover { background: #555555; }
            """)
            return btn

        self.btn_align_left = create_menu_btn("|<", "Align Left")
        self.btn_align_center = create_menu_btn("≡", "Align Center")
        self.btn_align_right = create_menu_btn(">|", "Align Right")
        self.btn_valign_top = create_menu_btn("⇡", "Align Top")
        self.btn_valign_middle = create_menu_btn("⇕", "Align Middle")
        self.btn_valign_bottom = create_menu_btn("⇣", "Align Bottom")
        
        self.btn_align_reset = create_reset_btn("Reset Alignment")

        align_layout.addWidget(self.btn_align_left, 0, 0)
        align_layout.addWidget(self.btn_align_center, 0, 1)
        align_layout.addWidget(self.btn_align_right, 0, 2)
        align_layout.addWidget(self.btn_valign_top, 1, 0)
        align_layout.addWidget(self.btn_valign_middle, 1, 1)
        align_layout.addWidget(self.btn_valign_bottom, 1, 2)
        align_layout.addWidget(self.btn_align_reset, 2, 0, 1, 3) 

        align_action = QWidgetAction(self)
        align_action.setDefaultWidget(align_widget)
        self.align_menu.addAction(align_action)
        self.btn_align.setMenu(self.align_menu)
        
        # --- Compact Spacing & Indent Menu ---
        self.btn_spacing = create_btn("↕", "Spacing & Indent")
        self.spacing_menu = QMenu(self)
        self.spacing_menu.setStyleSheet("border: none;")
        
        spacing_widget = QWidget()
        spacing_widget.setStyleSheet("QWidget { background-color: #333333; border: 1px solid #555555; }")
        spacing_layout = QGridLayout(spacing_widget)
        spacing_layout.setContentsMargins(6, 6, 6, 6)
        spacing_layout.setSpacing(6)
        
        lbl_line = QLabel("Line")
        lbl_line.setStyleSheet("color: white; border: none;")
        self.btn_line_space_minus = create_menu_btn("-", "Decrease Line Spacing")
        self.btn_line_space_plus = create_menu_btn("+", "Increase Line Spacing")
        
        lbl_indent = QLabel("Indent")
        lbl_indent.setStyleSheet("color: white; border: none;")
        self.btn_indent_minus = create_menu_btn("-", "Decrease Indent")
        self.btn_indent_plus = create_menu_btn("+", "Increase Indent")
        
        self.btn_spacing_reset = create_reset_btn("Reset Spacing")

        spacing_layout.addWidget(lbl_line, 0, 0)
        spacing_layout.addWidget(self.btn_line_space_minus, 0, 1)
        spacing_layout.addWidget(self.btn_line_space_plus, 0, 2)
        spacing_layout.addWidget(lbl_indent, 1, 0)
        spacing_layout.addWidget(self.btn_indent_minus, 1, 1)
        spacing_layout.addWidget(self.btn_indent_plus, 1, 2)
        spacing_layout.addWidget(self.btn_spacing_reset, 2, 0, 1, 3) 
        
        spacing_action = QWidgetAction(self)
        spacing_action.setDefaultWidget(spacing_widget)
        self.spacing_menu.addAction(spacing_action)
        self.btn_spacing.setMenu(self.spacing_menu)
        
        layout.addStretch()