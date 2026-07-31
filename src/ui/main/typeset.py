from PySide6.QtWidgets import (
    QWidget, QBoxLayout, QHBoxLayout, QPushButton, QMenu,
    QWidgetAction, QGridLayout, QToolButton, QLabel, QComboBox, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

class MenuContainerWidget(QWidget):
    """Custom widget to prevent clicks on empty grid spaces from accidentally closing the QMenu."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def mousePressEvent(self, event):
        event.accept()
    def mouseReleaseEvent(self, event):
        event.accept()

class TypesetToolBar(QWidget):
    """Contextual toolbar that appears next to the canvas for formatting."""

    position_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._current_pos = "right"
        self.positions = ["right", "bottom", "left", "top"]
        self._setup_ui()
        self.set_position(self._current_pos)

    def _setup_ui(self):
        self.main_layout = QBoxLayout(QBoxLayout.TopToBottom, self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignCenter)

        def create_btn(icon_text, tooltip):
            btn = QPushButton(icon_text)
            btn.setToolTip(tooltip)
            btn.setMinimumSize(38, 38)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 16px;
                    font-weight: bold;
                    border-radius: 4px;
                }
            """)
            self.main_layout.addWidget(btn)
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

        def create_menu_btn(icon_text, tooltip, auto_close=True, menu_ref=None):
            btn = QToolButton()
            btn.setText(icon_text)
            btn.setToolTip(tooltip)
            btn.setMinimumSize(34, 34)
            btn.setStyleSheet("""
                QToolButton { font-size: 16px; font-weight: bold; border-radius: 4px; background: transparent; color: white; border: none; }
                QToolButton:hover { background: #555555; }
            """)
            if auto_close and menu_ref:
                btn.clicked.connect(menu_ref.hide)
            return btn

        self.btn_cycle_pos = create_btn("⟲", "Move Toolbar Position")
        self.btn_cycle_pos.clicked.connect(self._cycle_position)

        self.btn_mask_bubble = create_btn("◩", "Generate Text Mask")
        self.btn_inpaint_bubble = create_btn("🖌", "Inpaint Mask")
        self.btn_toggle_typeset = create_btn("⊙", "Toggle Typeset Visibility")

        # ==========================================
        # FONT MENU
        # ==========================================
        self.btn_font = create_btn("A", "Font Controls")
        self.font_menu = QMenu(self)
        self.font_menu.setStyleSheet("border: none;")

        font_widget = MenuContainerWidget()
        font_widget.setObjectName("menuPanel")
        font_widget.setStyleSheet("#menuPanel { background-color: #333333; border: 1px solid #555555; }")
        font_layout = QGridLayout(font_widget)
        font_layout.setContentsMargins(6, 6, 6, 6)
        font_layout.setSpacing(6)

        # Row 0: Font Family Custom Dropdown
        self.font_combo = QComboBox()
        self.font_combo.setStyleSheet("""
            QComboBox { background: #444444; color: white; border: 1px solid #555555; padding: 2px; border-radius: 3px; }
            QAbstractItemView { background: #444444; color: white; selection-background-color: #555555; }
        """)
        self.font_combo.setMinimumWidth(150)
        self.font_combo.setMaxVisibleItems(15)

        self.btn_reload_fonts = create_menu_btn("⟳", "Reload Fonts", False)

        font_layout.addWidget(self.font_combo, 0, 0, 1, 3)
        font_layout.addWidget(self.btn_reload_fonts, 0, 3)

        # Row 1: Open Fonts Settings
        self.btn_open_fonts = create_reset_btn("Customize Fonts")
        font_layout.addWidget(self.btn_open_fonts, 1, 0, 1, 4)

        # Row 2: Font Size
        lbl_size = QLabel("Size")
        lbl_size.setStyleSheet("color: white; background: transparent; border: none;")

        self.spin_size = QSpinBox()
        self.spin_size.setRange(1, 999)
        self.spin_size.setValue(16)
        self.spin_size.setAlignment(Qt.AlignCenter)
        self.spin_size.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.spin_size.setStyleSheet("""
            QSpinBox { background: #444444; color: white; border: 1px solid #555555; padding: 2px; border-radius: 3px; }
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; }
        """)

        self.btn_size_minus = create_menu_btn("-", "Decrease Font Size", False)
        self.btn_size_plus = create_menu_btn("+", "Increase Font Size", False)

        size_layout = QHBoxLayout()
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(6)
        size_layout.addWidget(self.btn_size_minus)
        size_layout.addWidget(self.spin_size)
        size_layout.addWidget(self.btn_size_plus)

        font_layout.addWidget(lbl_size, 2, 0)
        font_layout.addLayout(size_layout, 2, 1, 1, 3)

        # Row 3: Styling Buttons
        self.btn_bold = create_menu_btn("B", "Toggle Bold", False)
        self.btn_bold.setStyleSheet(self.btn_bold.styleSheet() + " font-weight: 900;")
        self.btn_italic = create_menu_btn("I", "Toggle Italic", False)
        self.btn_italic.setStyleSheet(self.btn_italic.styleSheet() + " font-style: italic; font-weight: normal;")
        self.btn_underline = create_menu_btn("U", "Toggle Underline", False)
        self.btn_underline.setStyleSheet(self.btn_underline.styleSheet() + " text-decoration: underline; font-weight: normal;")
        self.btn_strike = create_menu_btn("S", "Toggle Strikeout", False)
        self.btn_strike.setStyleSheet(self.btn_strike.styleSheet() + " text-decoration: line-through; font-weight: normal;")

        style_layout = QHBoxLayout()
        style_layout.setContentsMargins(0, 0, 0, 0)
        style_layout.setSpacing(6)
        for btn in [self.btn_bold, self.btn_italic, self.btn_underline, self.btn_strike]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            style_layout.addWidget(btn)

        font_layout.addLayout(style_layout, 3, 0, 1, 4)

        # Row 4: Text Color
        lbl_text_color = QLabel("Text Color")
        lbl_text_color.setStyleSheet("color: white; background: transparent; border: none;")
        self.combo_text_color = QComboBox()
        self.combo_text_color.addItems(["Black", "White", "Red", "Blue", "Green", "Yellow"])
        self.combo_text_color.setStyleSheet("""
            QComboBox { background: #444444; color: white; border: 1px solid #555555; padding: 2px; border-radius: 3px; }
            QAbstractItemView { background: #444444; color: white; selection-background-color: #555555; }
        """)
        font_layout.addWidget(lbl_text_color, 4, 0)
        font_layout.addWidget(self.combo_text_color, 4, 1, 1, 3)

        # Row 5: Stroke Width
        lbl_stroke_width = QLabel("Stroke Size")
        lbl_stroke_width.setStyleSheet("color: white; background: transparent; border: none;")
        self.spin_stroke_width = QSpinBox()
        self.spin_stroke_width.setRange(0, 50)
        self.spin_stroke_width.setValue(0)
        self.spin_stroke_width.setAlignment(Qt.AlignCenter)
        self.spin_stroke_width.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.spin_stroke_width.setStyleSheet("""
            QSpinBox { background: #444444; color: white; border: 1px solid #555555; padding: 2px; border-radius: 3px; }
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; }
        """)
        self.btn_stroke_minus = create_menu_btn("-", "Decrease Stroke", False)
        self.btn_stroke_plus = create_menu_btn("+", "Increase Stroke", False)

        stroke_size_layout = QHBoxLayout()
        stroke_size_layout.setContentsMargins(0, 0, 0, 0)
        stroke_size_layout.setSpacing(6)
        stroke_size_layout.addWidget(self.btn_stroke_minus)
        stroke_size_layout.addWidget(self.spin_stroke_width)
        stroke_size_layout.addWidget(self.btn_stroke_plus)

        font_layout.addWidget(lbl_stroke_width, 5, 0)
        font_layout.addLayout(stroke_size_layout, 5, 1, 1, 3)

        # Row 6: Stroke Color
        lbl_stroke_color = QLabel("Stroke Color")
        lbl_stroke_color.setStyleSheet("color: white; background: transparent; border: none;")
        self.combo_stroke_color = QComboBox()
        self.combo_stroke_color.addItems(["White", "Black", "Red", "Blue", "Green", "Yellow"])
        self.combo_stroke_color.setStyleSheet("""
            QComboBox { background: #444444; color: white; border: 1px solid #555555; padding: 2px; border-radius: 3px; }
            QAbstractItemView { background: #444444; color: white; selection-background-color: #555555; }
        """)
        font_layout.addWidget(lbl_stroke_color, 6, 0)
        font_layout.addWidget(self.combo_stroke_color, 6, 1, 1, 3)

        # Row 7: Reset
        self.btn_font_reset = create_reset_btn("Reset Font / Stroke")
        font_layout.addWidget(self.btn_font_reset, 7, 0, 1, 4)

        font_action = QWidgetAction(self)
        font_action.setDefaultWidget(font_widget)
        self.font_menu.addAction(font_action)
        self.btn_font.setMenu(self.font_menu)

        # ==========================================
        # ALIGNMENT MENU
        # ==========================================
        self.btn_align = create_btn("≡", "Text Alignment")
        self.align_menu = QMenu(self)
        self.align_menu.setStyleSheet("border: none;")

        align_widget = MenuContainerWidget()
        align_widget.setObjectName("menuPanel")
        align_widget.setStyleSheet("#menuPanel { background-color: #333333; border: 1px solid #555555; }")
        align_layout = QGridLayout(align_widget)
        align_layout.setContentsMargins(6, 6, 6, 6)
        align_layout.setSpacing(6)

        self.btn_align_left = create_menu_btn("|<", "Align Left", False, self.align_menu)
        self.btn_align_center = create_menu_btn("≡", "Align Center", False, self.align_menu)
        self.btn_align_right = create_menu_btn(">|", "Align Right", False, self.align_menu)
        self.btn_valign_top = create_menu_btn("⇡", "Align Top", False, self.align_menu)
        self.btn_valign_middle = create_menu_btn("⇕", "Align Middle", False, self.align_menu)
        self.btn_valign_bottom = create_menu_btn("⇣", "Align Bottom", False, self.align_menu)

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

        # ==========================================
        # SPACING MENU
        # ==========================================
        self.btn_spacing = create_btn("↕", "Spacing & Indent")
        self.spacing_menu = QMenu(self)
        self.spacing_menu.setStyleSheet("border: none;")

        spacing_widget = MenuContainerWidget()
        spacing_widget.setObjectName("menuPanel")
        spacing_widget.setStyleSheet("#menuPanel { background-color: #333333; border: 1px solid #555555; }")
        spacing_layout = QGridLayout(spacing_widget)
        spacing_layout.setContentsMargins(6, 6, 6, 6)
        spacing_layout.setSpacing(6)

        lbl_line = QLabel("Line")
        lbl_line.setStyleSheet("color: white; background: transparent; border: none;")
        self.btn_line_space_minus = create_menu_btn("-", "Decrease Line Spacing", False)
        self.btn_line_space_plus = create_menu_btn("+", "Increase Line Spacing", False)

        lbl_indent = QLabel("Indent")
        lbl_indent.setStyleSheet("color: white; background: transparent; border: none;")
        self.btn_indent_minus = create_menu_btn("-", "Decrease Indent", False)
        self.btn_indent_plus = create_menu_btn("+", "Increase Indent", False)

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

    def set_position(self, pos):
        """Flips the toolbar's dimensions and flex-direction based on position."""
        self._current_pos = pos
        self.layout().invalidate()

        if pos in ["left", "right"]:
            self.main_layout.setDirection(QBoxLayout.TopToBottom)
            self.setMinimumSize(50, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        else:
            self.main_layout.setDirection(QBoxLayout.LeftToRight)
            self.setMinimumSize(0, 50)
            self.setMaximumSize(16777215, 16777215)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        border_css = {
            "right": "border-left: 1px solid #3c3c3c;",
            "left": "border-right: 1px solid #3c3c3c;",
            "top": "border-bottom: 1px solid #3c3c3c;",
            "bottom": "border-top: 1px solid #3c3c3c;"
        }

        self.setStyleSheet(f"""
            TypesetToolBar {{
                background-color: #2b2b2b;
                {border_css[pos]}
            }}
            QPushButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """)

    def _cycle_position(self):
        idx = self.positions.index(self._current_pos)
        next_pos = self.positions[(idx + 1) % len(self.positions)]
        self.position_requested.emit(next_pos)
