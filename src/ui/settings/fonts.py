import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QSpinBox, QComboBox, 
    QGridLayout, QCheckBox, QPushButton, QListWidget, QScrollArea, QMessageBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QDesktopServices
from src.core.downloaders import FontDownloadWorker

class FontsTab(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.font_downloader = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)

        # --- Default Font Configuration ---
        grp_defaults = QGroupBox("Default Font Properties")
        fd_layout = QGridLayout(grp_defaults)

        fd_layout.addWidget(QLabel("Family:"), 0, 0)
        self.def_font_combo = QComboBox()
        self.def_font_combo.addItems(self.main_window.get_font_families())
        def_fam = self.main_window.settings.value("default_font_family", "sans-serif")
        idx_fam = self.def_font_combo.findText(def_fam, Qt.MatchContains)
        if idx_fam >= 0:
            self.def_font_combo.setCurrentIndex(idx_fam)
        self.def_font_combo.currentTextChanged.connect(lambda f: self.main_window.settings.setValue("default_font_family", f))
        fd_layout.addWidget(self.def_font_combo, 0, 1, 1, 3)

        fd_layout.addWidget(QLabel("Size:"), 1, 0)
        self.def_size_spin = QSpinBox()
        self.def_size_spin.setRange(1, 999)
        self.def_size_spin.setValue(int(self.main_window.settings.value("default_font_size", 16)))
        self.def_size_spin.valueChanged.connect(lambda v: self.main_window.settings.setValue("default_font_size", v))
        fd_layout.addWidget(self.def_size_spin, 1, 1, 1, 3)

        self.def_chk_bold = QCheckBox("Bold")
        self.def_chk_bold.setChecked(self.main_window.settings.value("default_font_bold", False, type=bool))
        self.def_chk_bold.stateChanged.connect(lambda: self.main_window.settings.setValue("default_font_bold", self.def_chk_bold.isChecked()))

        self.def_chk_italic = QCheckBox("Italic")
        self.def_chk_italic.setChecked(self.main_window.settings.value("default_font_italic", False, type=bool))
        self.def_chk_italic.stateChanged.connect(lambda: self.main_window.settings.setValue("default_font_italic", self.def_chk_italic.isChecked()))

        self.def_chk_under = QCheckBox("Underline")
        self.def_chk_under.setChecked(self.main_window.settings.value("default_font_underline", False, type=bool))
        self.def_chk_under.stateChanged.connect(lambda: self.main_window.settings.setValue("default_font_underline", self.def_chk_under.isChecked()))

        self.def_chk_strike = QCheckBox("Strikeout")
        self.def_chk_strike.setChecked(self.main_window.settings.value("default_font_strikeout", False, type=bool))
        self.def_chk_strike.stateChanged.connect(lambda: self.main_window.settings.setValue("default_font_strikeout", self.def_chk_strike.isChecked()))

        fd_layout.addWidget(self.def_chk_bold, 2, 0)
        fd_layout.addWidget(self.def_chk_italic, 2, 1)
        fd_layout.addWidget(self.def_chk_under, 2, 2)
        fd_layout.addWidget(self.def_chk_strike, 2, 3)

        fd_layout.addWidget(QLabel("Align:"), 3, 0)
        self.def_align_combo = QComboBox()
        self.def_align_combo.addItems(["Left", "Center", "Right"])
        saved_align = self.main_window.settings.value("default_align", "center").lower()
        align_map = {"left": 0, "center": 1, "right": 2}
        self.def_align_combo.setCurrentIndex(align_map.get(saved_align, 1))
        self.def_align_combo.currentIndexChanged.connect(
            lambda idx: self.main_window.settings.setValue("default_align", ["left", "center", "right"][idx])
        )
        fd_layout.addWidget(self.def_align_combo, 3, 1)

        fd_layout.addWidget(QLabel("Indent:"), 3, 2)
        self.def_indent_spin = QSpinBox()
        self.def_indent_spin.setRange(0, 100)
        self.def_indent_spin.setValue(int(self.main_window.settings.value("default_indent", 5)))
        self.def_indent_spin.valueChanged.connect(lambda v: self.main_window.settings.setValue("default_indent", v))
        fd_layout.addWidget(self.def_indent_spin, 3, 3)

        fd_layout.addWidget(QLabel("Text Color:"), 4, 0)
        self.def_text_combo = QComboBox()
        self.def_text_combo.addItems(["Black", "White", "Red", "Blue", "Green", "Yellow"])
        saved_txt = self.main_window.settings.value("default_text_color", "black").capitalize()
        idx_txt = self.def_text_combo.findText(saved_txt)
        self.def_text_combo.setCurrentIndex(idx_txt if idx_txt >= 0 else 0)
        self.def_text_combo.currentTextChanged.connect(lambda t: self.main_window.settings.setValue("default_text_color", t.lower()))
        fd_layout.addWidget(self.def_text_combo, 4, 1)

        fd_layout.addWidget(QLabel("Stroke Width:"), 4, 2)
        self.def_stroke_spin = QSpinBox()
        self.def_stroke_spin.setRange(0, 50)
        self.def_stroke_spin.setValue(int(self.main_window.settings.value("default_stroke_width", 0)))
        self.def_stroke_spin.valueChanged.connect(lambda v: self.main_window.settings.setValue("default_stroke_width", v))
        fd_layout.addWidget(self.def_stroke_spin, 4, 3)

        fd_layout.addWidget(QLabel("Stroke Color:"), 5, 0)
        self.def_stroke_combo = QComboBox()
        self.def_stroke_combo.addItems(["White", "Black", "Red", "Blue", "Green", "Yellow"])
        saved_color = self.main_window.settings.value("default_stroke_color", "white").capitalize()
        idx = self.def_stroke_combo.findText(saved_color)
        self.def_stroke_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.def_stroke_combo.currentTextChanged.connect(lambda t: self.main_window.settings.setValue("default_stroke_color", t.lower()))
        fd_layout.addWidget(self.def_stroke_combo, 5, 1)

        layout.addWidget(grp_defaults)

        # --- Smart Auto-Styling ---
        grp_auto_style = QGroupBox("Smart Auto-Styling (Enhances Legibility on Mask Generation)")
        auto_style_layout = QVBoxLayout(grp_auto_style)

        self.chk_auto_style_enabled = QCheckBox("Enable Smart Auto-Styling")
        self.chk_auto_style_enabled.setChecked(self.main_window.settings.value("auto_style_enabled", True, type=bool))
        self.chk_auto_style_enabled.stateChanged.connect(lambda: self.main_window.settings.setValue("auto_style_enabled", self.chk_auto_style_enabled.isChecked()))
        auto_style_layout.addWidget(self.chk_auto_style_enabled)

        auto_options_layout = QVBoxLayout()
        auto_options_layout.setContentsMargins(20, 0, 0, 0)

        self.chk_auto_style_color = QCheckBox("Auto-flip text color (Black/White) based on background")
        self.chk_auto_style_color.setChecked(self.main_window.settings.value("auto_style_color", True, type=bool))
        self.chk_auto_style_color.stateChanged.connect(lambda: self.main_window.settings.setValue("auto_style_color", self.chk_auto_style_color.isChecked()))
        auto_options_layout.addWidget(self.chk_auto_style_color)

        stroke_size_layout = QHBoxLayout()
        self.chk_auto_style_stroke = QCheckBox("Auto-apply stroke on noisy or gray backgrounds")
        self.chk_auto_style_stroke.setChecked(self.main_window.settings.value("auto_style_stroke", True, type=bool))
        self.chk_auto_style_stroke.stateChanged.connect(lambda: self.main_window.settings.setValue("auto_style_stroke", self.chk_auto_style_stroke.isChecked()))
        stroke_size_layout.addWidget(self.chk_auto_style_stroke)

        stroke_size_layout.addSpacing(10)
        stroke_size_layout.addWidget(QLabel("Stroke Size:"))
        self.auto_stroke_spin = QSpinBox()
        self.auto_stroke_spin.setRange(1, 50)
        self.auto_stroke_spin.setValue(int(self.main_window.settings.value("auto_stroke_size", 4)))
        self.auto_stroke_spin.valueChanged.connect(lambda v: self.main_window.settings.setValue("auto_stroke_size", v))
        stroke_size_layout.addWidget(self.auto_stroke_spin)
        stroke_size_layout.addStretch()

        auto_options_layout.addLayout(stroke_size_layout)
        auto_style_layout.addLayout(auto_options_layout)

        def _toggle_auto_style_opts(state):
            is_enabled = (state == Qt.Checked.value) if isinstance(state, int) else state
            self.chk_auto_style_color.setEnabled(is_enabled)
            self.chk_auto_style_stroke.setEnabled(is_enabled)
            self.auto_stroke_spin.setEnabled(is_enabled)

        self.chk_auto_style_enabled.stateChanged.connect(_toggle_auto_style_opts)
        _toggle_auto_style_opts(self.chk_auto_style_enabled.isChecked())

        layout.addWidget(grp_auto_style)

        # --- Custom Local Fonts ---
        fonts_info = QLabel("<b>Custom Fonts Directory</b><br>Drop .ttf or .otf files into the local fonts folder to use them.")
        layout.addWidget(fonts_info)

        h_layout = QHBoxLayout()
        self.font_list = QListWidget()
        for font in self.main_window.external_fonts:
            self.font_list.addItem(font)
        self.font_list.currentTextChanged.connect(self._update_font_preview)

        self.font_preview = QLabel("The quick brown fox jumps over the lazy dog\n0123456789")
        self.font_preview.setAlignment(Qt.AlignCenter)
        self.font_preview.setStyleSheet("background-color: #333; border: 1px solid #555; border-radius: 4px; padding: 10px; font-size: 24px;")
        self.font_preview.setMinimumWidth(250)
        self.font_preview.setWordWrap(True)

        h_layout.addWidget(self.font_list)
        h_layout.addWidget(self.font_preview)
        layout.addLayout(h_layout)

        btn_fonts_layout = QHBoxLayout()

        self.btn_dl_font = QPushButton("Download Anime Ace BB")
        self.btn_dl_font.clicked.connect(self._download_manga_font)
        self._update_font_dl_btn_state()

        btn_open_folder = QPushButton("Open Fonts Folder")
        btn_open_folder.clicked.connect(self._open_fonts_folder)
        btn_reload = QPushButton("Reload Fonts")
        btn_reload.clicked.connect(self._reload_fonts_from_settings)

        btn_fonts_layout.addWidget(self.btn_dl_font)
        btn_fonts_layout.addWidget(btn_open_folder)
        btn_fonts_layout.addWidget(btn_reload)
        layout.addLayout(btn_fonts_layout)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def _update_font_dl_btn_state(self):
        fonts_dir = os.path.join(os.getcwd(), "fonts")
        is_downloaded = False
        if os.path.exists(fonts_dir):
            for f in os.listdir(fonts_dir):
                if "animeace" in f.lower():
                    is_downloaded = True
                    break

        if is_downloaded:
            self.btn_dl_font.setEnabled(False)
            self.btn_dl_font.setText("Anime Ace BB Downloaded")
            self.btn_dl_font.setStyleSheet("background-color: #444444; color: #aaaaaa;")
        else:
            self.btn_dl_font.setEnabled(True)
            self.btn_dl_font.setText("Download Anime Ace BB")
            self.btn_dl_font.setStyleSheet("background-color: #0056b3; color: white;")

    def _download_manga_font(self):
        if self.font_downloader and self.font_downloader.isRunning():
            return
        self.btn_dl_font.setEnabled(False)
        self.btn_dl_font.setText("Downloading...")
        self.btn_dl_font.setStyleSheet("background-color: #444444; color: #aaaaaa;")

        self.font_downloader = FontDownloadWorker()
        self.font_downloader.process_finished.connect(self._on_font_downloaded)
        self.font_downloader.start()

    def _on_font_downloaded(self, success, msg):
        self._update_font_dl_btn_state()
        if success:
            QMessageBox.information(self, "Success", msg)
            self._reload_fonts_from_settings()
        else:
            QMessageBox.warning(self, "Download Failed", f"Failed to download font: {msg}")

    def _update_font_preview(self, font_family):
        if font_family:
            self.font_preview.setFont(QFont(font_family, 24))

    def _open_fonts_folder(self):
        fonts_dir = os.path.join(os.getcwd(), "fonts")
        os.makedirs(fonts_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(fonts_dir))

    def _reload_fonts_from_settings(self):
        self.main_window.reload_custom_fonts()
        self.font_list.clear()
        for font in self.main_window.external_fonts:
            self.font_list.addItem(font)

        self.def_font_combo.blockSignals(True)
        self.def_font_combo.clear()
        self.def_font_combo.addItems(self.main_window.get_font_families())

        def_fam = self.main_window.settings.value("default_font_family", "sans-serif")
        idx_fam = self.def_font_combo.findText(def_fam, Qt.MatchContains)
        if idx_fam >= 0:
            self.def_font_combo.setCurrentIndex(idx_fam)
        self.def_font_combo.blockSignals(False)

        self._update_font_dl_btn_state()