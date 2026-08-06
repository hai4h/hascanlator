from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QScrollArea, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from src.ui.settings.widgets import AdaptiveKeySequenceEdit

class KeybindsTab(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.keybind_edits = {}
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        scroll_content = QWidget()
        layout = QFormLayout(scroll_content)

        lbl_desc = QLabel("<b>Custom Keybindings</b><br>Click the input field and press a key sequence to bind it. <i>Note: Bindings are active when the canvas area is in focus.</i>")
        lbl_desc.setWordWrap(True)
        layout.addRow(lbl_desc)

        def add_header(title):
            lbl = QLabel(f"<b>{title}</b>")
            lbl.setStyleSheet("padding-top: 15px; color: #aaa; font-size: 14px;")
            layout.addRow(lbl)

        def add_bind(label, setting_key, default_val=""):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            edit = AdaptiveKeySequenceEdit(QKeySequence(self.main_window.settings.value(setting_key, default_val)))
            edit.keySequenceChanged.connect(lambda ks, sk=setting_key: self._on_keybind_changed(sk, ks))

            btn_clear = QPushButton("✕")
            btn_clear.setFixedWidth(28)
            btn_clear.setToolTip("Clear keybind")
            btn_clear.clicked.connect(edit.clear)

            row_layout.addWidget(edit)
            row_layout.addWidget(btn_clear)

            self.keybind_edits[setting_key] = edit
            layout.addRow(label, row_widget)

        add_header("File and Workspace")
        add_bind("Load Images:", "keybind_load_images")
        add_bind("Reset Workspace:", "keybind_reset_workspace")
        add_bind("Open Settings:", "keybind_open_settings")

        add_header("Navigation")
        add_bind("Next Page:", "keybind_next_page")
        add_bind("Previous Page:", "keybind_prev_page")

        add_header("Canvas and Selection")
        add_bind("Select All Boxes:", "keybind_select_all", "Ctrl+A")
        add_bind("Delete Selected Box(es):", "keybind_delete_box", "Del")
        add_bind("Add Box (Manual):", "keybind_add_box")
        add_bind("Undo Action:", "keybind_undo_edit")
        add_bind("Redo Action:", "keybind_redo_edit")

        add_header("AI and Processing")
        add_bind("Auto Detect Text (YOLO):", "keybind_auto_detect")
        add_bind("Run OCR on Selected:", "keybind_run_ocr")
        add_bind("Translate Selected Box:", "keybind_translate_box")
        add_bind("Translate + Typeset Selected:", "keybind_trans_type_sel")
        add_bind("Generate Text Mask:", "keybind_generate_mask")
        add_bind("Inpaint Mask:", "keybind_inpaint_bubble")

        add_header("Typesetting and Formatting")
        add_bind("Toggle Typeset Visibility:", "keybind_toggle_typeset")
        add_bind("Toggle Bold:", "keybind_bold")
        add_bind("Toggle Italic:", "keybind_italic")
        add_bind("Toggle Underline:", "keybind_underline")
        add_bind("Toggle Strikeout:", "keybind_strikeout")

        add_header("Text Alignment")
        add_bind("Align Left:", "keybind_align_left")
        add_bind("Align Center:", "keybind_align_center")
        add_bind("Align Right:", "keybind_align_right")

        add_header("Adjustment Controls")
        add_bind("Increase Font Size:", "keybind_font_up")
        add_bind("Decrease Font Size:", "keybind_font_down")
        add_bind("Increase Line Spacing:", "keybind_line_space_up")
        add_bind("Decrease Line Spacing:", "keybind_line_space_down")
        add_bind("Increase Indent:", "keybind_indent_up")
        add_bind("Decrease Indent:", "keybind_indent_down")

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        self._validate_keybinds()

    def _on_keybind_changed(self, setting_key, key_sequence):
        self.main_window.settings.setValue(setting_key, key_sequence.toString())
        self._validate_keybinds()
        self.main_window.reload_shortcuts()

    def _validate_keybinds(self):
        seq_counts = {}
        for edit in self.keybind_edits.values():
            ks_str = edit.keySequence().toString()
            if ks_str:
                seq_counts[ks_str] = seq_counts.get(ks_str, 0) + 1

        for edit in self.keybind_edits.values():
            ks_str = edit.keySequence().toString()
            if ks_str and seq_counts.get(ks_str, 0) > 1:
                edit.setStyleSheet("border: 1px solid #ff6666; background-color: rgba(255, 102, 102, 0.15);")
                edit.setToolTip("Duplicate keybind! This shortcut is disabled until resolved.")
            else:
                edit.setStyleSheet("")
                edit.setToolTip("")