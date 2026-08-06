from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt

class ShortcutsMixin:
    def _setup_shortcuts(self):
        self.shortcuts = {}
        bindings = [
            ("keybind_load_images", self.load_images_dialog),
            ("keybind_reset_workspace", self.reset_workspace),
            ("keybind_open_settings", lambda: self.open_settings()),
            ("keybind_next_page", self.next_image),
            ("keybind_prev_page", self.prev_image),
            ("keybind_select_all", self.select_all_boxes),
            ("keybind_delete_box", self.delete_selected_box),
            ("keybind_add_box", self.add_test_box),
            ("keybind_undo_edit", self.undo_edit),
            ("keybind_redo_edit", self.redo_edit),
            ("keybind_auto_detect", self.run_auto_detect),
            ("keybind_run_ocr", self.run_ocr_on_selected),
            ("keybind_translate_box", self.run_translation_on_selected),
            ("keybind_trans_type_sel", self.run_translate_typeset_selected),
            ("keybind_generate_mask", self.generate_bubble_mask),
            ("keybind_inpaint_bubble", self.inpaint_bubble_mask),
            ("keybind_toggle_typeset", self.toggle_typeset_view),
            ("keybind_bold", self.toggle_text_bold),
            ("keybind_italic", self.toggle_text_italic),
            ("keybind_underline", self.toggle_text_underline),
            ("keybind_strikeout", self.toggle_text_strikeout),
            ("keybind_align_left", lambda: self.set_text_alignment(Qt.AlignLeft)),
            ("keybind_align_center", lambda: self.set_text_alignment(Qt.AlignCenter)),
            ("keybind_align_right", lambda: self.set_text_alignment(Qt.AlignRight)),
            ("keybind_font_up", lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() + 1)),
            ("keybind_font_down", lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() - 1)),
            ("keybind_line_space_up", lambda: self.set_text_line_spacing(0.1)),
            ("keybind_line_space_down", lambda: self.set_text_line_spacing(-0.1)),
            ("keybind_indent_up", lambda: self.set_text_indent(5)),
            ("keybind_indent_down", lambda: self.set_text_indent(-5)),
        ]

        for key, func in bindings:
            sc = QShortcut(self.view)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(func)
            self.shortcuts[key] = sc
        self.reload_shortcuts()

    def reload_shortcuts(self):
        seq_counts = {}
        for key in self.shortcuts.keys():
            default_val = "Ctrl+A" if key == "keybind_select_all" else "Del" if key == "keybind_delete_box" else ""
            val = self.settings.value(key, default_val)
            if val: seq_counts[val] = seq_counts.get(val, 0) + 1

        for key, sc in self.shortcuts.items():
            default_val = "Ctrl+A" if key == "keybind_select_all" else "Del" if key == "keybind_delete_box" else ""
            val = self.settings.value(key, default_val)
            if val and seq_counts.get(val, 0) == 1:
                sc.setKey(QKeySequence(val))
                sc.setEnabled(True)
            else:
                sc.setKey(QKeySequence())
                sc.setEnabled(False)