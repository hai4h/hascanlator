import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFont, QColor
from PySide6.QtWidgets import QListWidget

class FontManagementMixin:
    def reload_custom_fonts(self):
        if hasattr(self, '_loaded_font_ids'):
            for fid in self._loaded_font_ids:
                QFontDatabase.removeApplicationFont(fid)
        self._loaded_font_ids = []

        fonts_dir = os.path.join(os.getcwd(), "fonts")
        os.makedirs(fonts_dir, exist_ok=True)
        self.external_fonts = []
        file_count = 0

        for root, _, files in os.walk(fonts_dir):
            for filename in files:
                # Skip hidden macOS archive artifacts that get bundled in font ZIPs
                if filename.startswith('._'):
                    continue

                if filename.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
                    font_path = os.path.join(root, filename)
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    if font_id != -1:
                        self._loaded_font_ids.append(font_id)
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        for family in families:
                            if family not in self.external_fonts:
                                self.external_fonts.append(family)
                        file_count += 1

        if file_count > 0:
            self.statusBar().showMessage(f"Loaded {len(self.external_fonts)} custom font family(s) from {file_count} files.")
        self.refresh_font_combo()

    def refresh_font_combo(self, current_font=None):
        combo = self.typeset_toolbar.font_combo
        combo.blockSignals(True)
        combo.clear()
        all_fonts = QFontDatabase.families()

        def add_header(text):
            combo.addItem(text)
            idx = combo.count() - 1
            model = combo.model()
            item = model.item(idx)
            if item:
                item.setEnabled(False)
                item.setBackground(QColor("#333333"))
                item.setForeground(QColor("#aaaaaa"))
                f = item.font(); f.setBold(True); item.setFont(f)

        def add_font_item(family):
            combo.addItem(family)
            idx = combo.count() - 1
            combo.setItemData(idx, family, Qt.UserRole)
            combo.setItemData(idx, QFont(family), Qt.FontRole)

        if current_font:
            add_header("--- CURRENT ---")
            add_font_item(current_font)
        if self.recent_fonts:
            add_header("--- RECENT ---")
            for f in self.recent_fonts: add_font_item(f)
        if self.external_fonts:
            add_header("--- EXTERNAL ---")
            for f in self.external_fonts: add_font_item(f)

        add_header("--- ALL FONTS ---")
        for f in all_fonts: add_font_item(f)

        if current_font: combo.setCurrentIndex(1)
        combo.blockSignals(False)

    def _on_font_combo_changed(self, index):
        family = self.typeset_toolbar.font_combo.itemData(index, Qt.UserRole)
        if family: self.set_text_font_family(family)
