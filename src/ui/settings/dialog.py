import os
import urllib.request
import zipfile
import io
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QGroupBox, QSpinBox, QFontComboBox, QGridLayout,
    QPushButton, QTabWidget, QCheckBox, QMessageBox, QComboBox, QStackedWidget, QListWidget,
    QFormLayout, QKeySequenceEdit, QScrollArea
)
from PySide6.QtCore import Qt, QUrl, QThread, Signal
from PySide6.QtGui import QFont, QDesktopServices, QKeySequence
from huggingface_hub import scan_cache_dir

class AdaptiveKeySequenceEdit(QKeySequenceEdit):
    def __init__(self, key_sequence, parent=None):
        super().__init__(key_sequence, parent)
        self.setMaximumSequenceLength(1)

    def keyPressEvent(self, event):
        key = event.key()
        # Don't clear if the user is just pressing/holding down a modifier key
        if key not in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_unknown):
            # Block signals temporarily so it doesn't trigger a blank save before the new key registers
            self.blockSignals(True)
            self.clear()
            self.blockSignals(False)
        super().keyPressEvent(event)


# --- FONT DOWNLOAD WORKER ---
class FontDownloadWorker(QThread):
    finished = Signal(bool, str)
    def run(self):
        try:
            url = "https://dl.dafont.com/dl/?f=anime_ace_bb"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req) as response:
                with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                    fonts_dir = os.path.join(os.getcwd(), "fonts")
                    os.makedirs(fonts_dir, exist_ok=True)
                    for file_info in z.infolist():
                        if file_info.filename.lower().endswith(('.ttf', '.otf')):
                            z.extract(file_info, fonts_dir)
            self.finished.emit(True, "Anime Ace BB downloaded and installed successfully!")
        except Exception as e:
            self.finished.emit(False, str(e))

class SettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Settings & Model Manager")
        self.resize(650, 600)

        self.main_window.model_status_changed.connect(self.update_ui_state)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # ==========================================
        # TAB 1: VISION MODELS
        # ==========================================
        models_tab = QWidget()
        self.models_layout = QVBoxLayout(models_tab)

        chk_mirror = QCheckBox("Use HuggingFace Mirror (hf-mirror.com) to bypass network restrictions")
        chk_mirror.setChecked(self.main_window.settings.value("use_hf_mirror", False, type=bool))
        chk_mirror.stateChanged.connect(self._on_mirror_changed)
        self.models_layout.addWidget(chk_mirror)

        global_btns_layout = QHBoxLayout()
        btn_load_all = QPushButton("Load All Available")
        btn_load_all.setStyleSheet("font-weight: bold; padding: 8px;")
        btn_load_all.clicked.connect(self.load_all_models)

        btn_unload_all = QPushButton("Unload All")
        btn_unload_all.setStyleSheet("font-weight: bold; padding: 8px;")
        btn_unload_all.clicked.connect(self.unload_all_models)

        global_btns_layout.addWidget(btn_load_all)
        global_btns_layout.addWidget(btn_unload_all)

        self.models_layout.addLayout(global_btns_layout)
        self.models_layout.addWidget(QLabel("<hr>"))

        self.model_widgets = {}

        def add_model_ui(parent_layout, title, desc, load_key, repo_id, setting_key):
            repo_getter = lambda r=repo_id: r() if callable(r) else r
            model_layout = QVBoxLayout()

            header_layout = QHBoxLayout()
            header_layout.addWidget(QLabel(f"<b>{title}</b><br>{desc}"))
            disk_lbl = QLabel()
            header_layout.addWidget(disk_lbl, alignment=Qt.AlignRight | Qt.AlignTop)
            model_layout.addLayout(header_layout)

            status_lbl = QLabel()
            model_layout.addWidget(status_lbl)

            btn_layout = QHBoxLayout()
            btn_load = QPushButton("Load Model")
            btn_load.clicked.connect(lambda: self.main_window.load_model(load_key))

            btn_unload = QPushButton("Unload (Free RAM)")
            btn_unload.clicked.connect(lambda: self.main_window.unload_model(load_key))

            btn_delete = QPushButton("Delete from Disk")
            btn_delete.setStyleSheet("color: #d9534f;")
            btn_delete.clicked.connect(lambda k=load_key, g=repo_getter: self.delete_model(k, g()))

            btn_layout.addWidget(btn_load)
            btn_layout.addWidget(btn_unload)
            btn_layout.addWidget(btn_delete)
            model_layout.addLayout(btn_layout)

            chk_auto = QCheckBox("Auto-load on next launch")
            chk_auto.setChecked(self.main_window.settings.value(setting_key, False, type=bool))
            chk_auto.stateChanged.connect(lambda state, key=setting_key, chk=chk_auto:
                                          self.main_window.settings.setValue(key, chk.isChecked()))
            model_layout.addWidget(chk_auto)

            model_layout.addWidget(QLabel("<hr>"))
            parent_layout.addLayout(model_layout)

            self.model_widgets[load_key] = {
                "status_lbl": status_lbl, "disk_lbl": disk_lbl,
                "btn_load": btn_load, "btn_unload": btn_unload, "btn_delete": btn_delete,
                "chk_auto": chk_auto, "setting_key": setting_key, "repo_id": repo_id,
                "get_repo_id": repo_getter
            }

        add_model_ui(self.models_layout, "MangaOCR (Text Recognition)", "Reads Japanese text inside the boxes.", "manga_ocr", "kha-white/manga-ocr-base", "auto_load_mocr")
        add_model_ui(self.models_layout, "YOLOv8 Bubble Detector", "Accurate speech bubble locator.", "yolo_detector", "ogkalu/manga-text-detector-yolov8s", "auto_load_yolo")
        self.models_layout.addStretch()

        # ==========================================
        # TAB 2: TRANSLATION SETTINGS
        # ==========================================
        trans_tab = QWidget()
        trans_layout = QVBoxLayout(trans_tab)

        engine_layout = QHBoxLayout()
        engine_layout.addWidget(QLabel("<b>Translation Method:</b>"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Online API", "Local Offline NMT"])

        current_engine = self.main_window.settings.value("translation_engine", "google")
        self.engine_combo.setCurrentIndex(0 if current_engine == "google" else 1)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)

        engine_layout.addWidget(self.engine_combo)
        trans_layout.addLayout(engine_layout)
        trans_layout.addWidget(QLabel("<hr>"))

        self.trans_stack = QStackedWidget()

        online_page = QWidget()
        online_layout = QVBoxLayout(online_page)

        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("API Provider:"))
        api_combo = QComboBox()
        api_combo.addItems(["Google Translate"])
        api_combo.setEnabled(False)
        api_layout.addWidget(api_combo)
        online_layout.addLayout(api_layout)

        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Input Language:"))
        self.src_combo = QComboBox()
        lang_layout.addWidget(QLabel("Target Language:"))
        self.tgt_combo = QComboBox()

        self.langs_src = {"Auto Detect": "auto", "Japanese": "ja", "English": "en", "Korean": "ko", "Chinese (Simplified)": "zh-CN", "Vietnamese": "vi", "Spanish": "es", "French": "fr"}
        self.langs_tgt = {"English": "en", "Vietnamese": "vi", "Spanish": "es", "French": "fr", "Japanese": "ja", "Korean": "ko", "Chinese (Simplified)": "zh-CN"}

        self.src_combo.addItems(list(self.langs_src.keys()))
        self.tgt_combo.addItems(list(self.langs_tgt.keys()))

        saved_src = self.main_window.settings.value("trans_src", "ja")
        saved_tgt = self.main_window.settings.value("trans_tgt", "en")

        src_idx = list(self.langs_src.values()).index(saved_src) if saved_src in self.langs_src.values() else 1
        tgt_idx = list(self.langs_tgt.values()).index(saved_tgt) if saved_tgt in self.langs_tgt.values() else 0

        self.src_combo.setCurrentIndex(src_idx)
        self.tgt_combo.setCurrentIndex(tgt_idx)

        self.src_combo.currentIndexChanged.connect(self._save_langs)
        self.tgt_combo.currentIndexChanged.connect(self._save_langs)

        lang_layout.addWidget(self.src_combo)
        lang_layout.addWidget(self.tgt_combo)
        online_layout.addLayout(lang_layout)
        online_layout.addStretch()
        self.trans_stack.addWidget(online_page)

        nmt_page = QWidget()
        nmt_layout = QVBoxLayout(nmt_page)

        nmt_info_layout = QHBoxLayout()
        nmt_info_layout.addWidget(QLabel("Model Provider:"))
        self.nmt_mod_combo = QComboBox()

        nmt_repos = ["Helsinki-NLP/opus-mt-ja-en", "facebook/nllb-200-distilled-600M"]
        self.nmt_mod_combo.addItems(nmt_repos)

        saved_nmt = self.main_window.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en")
        if saved_nmt in nmt_repos:
            self.nmt_mod_combo.setCurrentIndex(nmt_repos.index(saved_nmt))

        self.nmt_mod_combo.currentIndexChanged.connect(self._on_nmt_repo_changed)
        nmt_info_layout.addWidget(self.nmt_mod_combo)
        nmt_layout.addLayout(nmt_info_layout)

        nmt_lang_layout = QHBoxLayout()

        nmt_lang_layout.addWidget(QLabel("Input Language:"))
        self.nmt_src = QComboBox()
        self.nmt_src.addItems(list(self.langs_src.keys()))
        self.nmt_src.setCurrentIndex(src_idx)
        self.nmt_src.currentIndexChanged.connect(self._save_nmt_langs)
        nmt_lang_layout.addWidget(self.nmt_src)

        nmt_lang_layout.addWidget(QLabel("Target Language:"))
        self.nmt_tgt = QComboBox()
        self.nmt_tgt.addItems(list(self.langs_tgt.keys()))
        self.nmt_tgt.setCurrentIndex(tgt_idx)
        self.nmt_tgt.currentIndexChanged.connect(self._save_nmt_langs)
        nmt_lang_layout.addWidget(self.nmt_tgt)

        nmt_layout.addLayout(nmt_lang_layout)

        nmt_layout.addWidget(QLabel("<hr>"))
        add_model_ui(nmt_layout, "NMT Engine", "Processes translation locally on your device.", "nmt_translator",
                     lambda: self.main_window.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en"), "auto_load_nmt")
        nmt_layout.addStretch()
        self.trans_stack.addWidget(nmt_page)

        trans_layout.addWidget(self.trans_stack)
        self.trans_stack.setCurrentIndex(0 if current_engine == "google" else 1)

        self._update_nmt_lang_states()

        # ==========================================
        # TAB 3: FONTS SETTINGS
        # ==========================================
        fonts_tab = QWidget()
        fonts_layout = QVBoxLayout(fonts_tab)

        # --- Default Font Configuration ---
        grp_defaults = QGroupBox("Default Font Properties")
        fd_layout = QGridLayout(grp_defaults)

        fd_layout.addWidget(QLabel("Family:"), 0, 0)
        self.def_font_combo = QFontComboBox()
        def_fam = self.main_window.settings.value("default_font_family", "sans-serif")
        self.def_font_combo.setCurrentFont(QFont(def_fam))
        self.def_font_combo.currentFontChanged.connect(lambda f: self.main_window.settings.setValue("default_font_family", f.family()))
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

        fonts_layout.addWidget(grp_defaults)

        # --- Custom Local Fonts ---
        fonts_info = QLabel("<b>Custom Fonts Directory</b><br>Drop .ttf or .otf files into the local fonts folder to use them.")
        fonts_layout.addWidget(fonts_info)

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
        fonts_layout.addLayout(h_layout)

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
        fonts_layout.addLayout(btn_fonts_layout)

        # ==========================================
        # TAB 4: KEYBINDS
        # ==========================================
        keybinds_tab = QWidget()
        keybinds_main_layout = QVBoxLayout(keybinds_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        scroll_content = QWidget()
        keybinds_layout = QFormLayout(scroll_content)

        lbl_keybinds_desc = QLabel("<b>Custom Keybindings</b><br>Click the input field and press a key sequence to bind it. <i>Note: Bindings are active when the canvas area is in focus.</i>")
        lbl_keybinds_desc.setWordWrap(True)
        keybinds_layout.addRow(lbl_keybinds_desc)

        self.keybind_edits = {}

        def add_header(title):
            lbl = QLabel(f"<b>{title}</b>")
            lbl.setStyleSheet("padding-top: 15px; color: #aaa; font-size: 14px;")
            keybinds_layout.addRow(lbl)

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
            keybinds_layout.addRow(label, row_widget)

        add_header("File & Workspace")
        add_bind("Load Images:", "keybind_load_images")
        add_bind("Reset Workspace:", "keybind_reset_workspace")
        add_bind("Open Settings:", "keybind_open_settings")

        add_header("Navigation")
        add_bind("Next Page:", "keybind_next_page")
        add_bind("Previous Page:", "keybind_prev_page")

        add_header("Canvas & Selection")
        add_bind("Select All Boxes:", "keybind_select_all", "Ctrl+A")
        add_bind("Delete Selected Box(es):", "keybind_delete_box", "Del")
        add_bind("Add Box (Manual):", "keybind_add_box")
        add_bind("Undo Image Edit:", "keybind_undo_edit")

        add_header("AI & Processing")
        add_bind("Auto Detect Text (YOLO):", "keybind_auto_detect")
        add_bind("Run OCR on Selected:", "keybind_run_ocr")
        add_bind("Translate Selected Box:", "keybind_translate_box")
        add_bind("Translate & Typeset Selected:", "keybind_trans_type_sel")
        add_bind("Translate & Typeset All:", "keybind_trans_type_all")
        add_bind("Smart Clean Bubble:", "keybind_smart_clean")

        add_header("Typesetting & Formatting")
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
        keybinds_main_layout.addWidget(scroll_area)

        # --- COMPILE TABS ---
        self.tabs.addTab(models_tab, "Detection")
        self.tabs.addTab(trans_tab, "Translation")
        self.tabs.addTab(fonts_tab, "Fonts")
        self.tabs.addTab(keybinds_tab, "Keybinds")
        layout.addWidget(self.tabs)

        self.update_ui_state()
        self._validate_keybinds()

    def _on_mirror_changed(self, state):
        is_checked = state == 2  # 2 corresponds to Qt.Checked
        self.main_window.settings.setValue("use_hf_mirror", is_checked)
        if is_checked:
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        else:
            os.environ.pop("HF_ENDPOINT", None)

    def _on_keybind_changed(self, setting_key, key_sequence):
        self.main_window.settings.setValue(setting_key, key_sequence.toString())
        self._validate_keybinds()
        self.main_window.reload_shortcuts()

    def _validate_keybinds(self):
        seq_counts = {}
        # Count occurrences of all non-empty key sequences
        for edit in self.keybind_edits.values():
            ks_str = edit.keySequence().toString()
            if ks_str:
                seq_counts[ks_str] = seq_counts.get(ks_str, 0) + 1

        # Apply red highlighting to duplicates
        for edit in self.keybind_edits.values():
            ks_str = edit.keySequence().toString()
            if ks_str and seq_counts.get(ks_str, 0) > 1:
                edit.setStyleSheet("border: 1px solid #ff6666; background-color: rgba(255, 102, 102, 0.15);")
                edit.setToolTip("Duplicate keybind! This shortcut is disabled until resolved.")
            else:
                edit.setStyleSheet("")
                edit.setToolTip("")

    def closeEvent(self, event):
        try:
            self.main_window.model_status_changed.disconnect(self.update_ui_state)
        except Exception:
            pass
        super().closeEvent(event)

    # --- FONT DOWNLOADER HELPERS ---
    def _update_font_dl_btn_state(self):
        """Checks if Anime Ace is already in the fonts folder and updates the button UI."""
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
        self.btn_dl_font.setEnabled(False)
        self.btn_dl_font.setText("Downloading...")
        self.btn_dl_font.setStyleSheet("background-color: #444444; color: #aaaaaa;")

        self.font_downloader = FontDownloadWorker()
        self.font_downloader.finished.connect(self._on_font_downloaded)
        self.font_downloader.start()

    def _on_font_downloaded(self, success, msg):
        self._update_font_dl_btn_state() # Refresh state based on download result
        if success:
            QMessageBox.information(self, "Success", msg)
            self._reload_fonts_from_settings()
        else:
            QMessageBox.warning(self, "Download Failed", f"Failed to download font: {msg}")

    # --- OTHER HELPERS ---
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

        def_fam = self.main_window.settings.value("default_font_family", "sans-serif")
        self.def_font_combo.setCurrentFont(QFont(def_fam))

        self._update_font_dl_btn_state()

    # --- MODEL & TRANSLATION SETTING HELPERS ---
    def _on_engine_changed(self, index):
        engine = "google" if index == 0 else "nmt"
        self.main_window.settings.setValue("translation_engine", engine)
        self.trans_stack.setCurrentIndex(index)
        self.main_window.update_button_states()

    def _on_nmt_repo_changed(self, index):
        new_repo = "facebook/nllb-200-distilled-600M" if index == 1 else "Helsinki-NLP/opus-mt-ja-en"
        old_repo = self.main_window.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en")
        if new_repo != old_repo:
            self.main_window.settings.setValue("nmt_model_repo", new_repo)
            self._update_nmt_lang_states()
            if self.main_window.nmt_model is not None or self.main_window.nmt_is_loading:
                self.main_window.unload_model("nmt_translator")
                self.main_window.load_model("nmt_translator")
            self.update_ui_state()

    def _update_nmt_lang_states(self):
        repo = self.main_window.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en")
        if "nllb" in repo:
            self.nmt_src.setEnabled(True)
            self.nmt_tgt.setEnabled(True)
        else:
            if "ja" in self.langs_src.values():
                self.nmt_src.setCurrentIndex(list(self.langs_src.values()).index("ja"))
            if "en" in self.langs_tgt.values():
                self.nmt_tgt.setCurrentIndex(list(self.langs_tgt.values()).index("en"))
            self.nmt_src.setEnabled(False)
            self.nmt_tgt.setEnabled(False)

    def _save_nmt_langs(self):
        src_code = list(self.langs_src.values())[self.nmt_src.currentIndex()]
        tgt_code = list(self.langs_tgt.values())[self.nmt_tgt.currentIndex()]
        self.main_window.settings.setValue("trans_src", src_code)
        self.main_window.settings.setValue("trans_tgt", tgt_code)
        self.src_combo.blockSignals(True)
        self.tgt_combo.blockSignals(True)
        self.src_combo.setCurrentIndex(self.nmt_src.currentIndex())
        self.tgt_combo.setCurrentIndex(self.nmt_tgt.currentIndex())
        self.src_combo.blockSignals(False)
        self.tgt_combo.blockSignals(False)

    def _save_langs(self):
        src_code = list(self.langs_src.values())[self.src_combo.currentIndex()]
        tgt_code = list(self.langs_tgt.values())[self.tgt_combo.currentIndex()]
        self.main_window.settings.setValue("trans_src", src_code)
        self.main_window.settings.setValue("trans_tgt", tgt_code)
        self.nmt_src.blockSignals(True)
        self.nmt_tgt.blockSignals(True)
        self.nmt_src.setCurrentIndex(self.src_combo.currentIndex())
        self.nmt_tgt.setCurrentIndex(self.tgt_combo.currentIndex())
        self.nmt_src.blockSignals(False)
        self.nmt_tgt.blockSignals(False)

    def load_all_models(self):
        for key, w_dict in self.model_widgets.items():
            if not self.main_window.is_model_downloaded(w_dict["get_repo_id"]()): continue
            if key not in self.main_window.model_load_queue:
                is_loaded = False
                if key == "manga_ocr" and self.main_window.mocr_model: is_loaded = True
                if key == "yolo_detector" and self.main_window.yolo_model: is_loaded = True
                if key == "nmt_translator" and self.main_window.nmt_model: is_loaded = True
                if not is_loaded: self.main_window.load_model(key)

    def unload_all_models(self):
        for key in self.model_widgets.keys():
            is_loaded = False
            if key == "manga_ocr" and self.main_window.mocr_model: is_loaded = True
            if key == "yolo_detector" and self.main_window.yolo_model: is_loaded = True
            if key == "nmt_translator" and self.main_window.nmt_model: is_loaded = True
            if is_loaded: self.main_window.unload_model(key)

    def delete_model(self, load_key, repo_id):
        reply = QMessageBox.question(self, "Confirm Deletion", "Are you sure you want to delete this model from your disk? You will need to redownload it next time.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.main_window.unload_model(load_key)
            try:
                hf_cache_info = scan_cache_dir()
                for repo in hf_cache_info.repos:
                    if repo.repo_id == repo_id:
                        strategy = hf_cache_info.delete_revisions(*[rev.commit_hash for rev in repo.revisions])
                        strategy.execute()
                        break
                QMessageBox.information(self, "Success", "Model successfully deleted from disk.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete model cache: {e}")
            self.update_ui_state()

    def _apply_state(self, is_loaded, is_loading, is_queued, w_dict):
        is_downloaded = self.main_window.is_model_downloaded(w_dict["get_repo_id"]())
        w_dict["chk_auto"].setEnabled(is_downloaded)
        if not is_downloaded:
            w_dict["chk_auto"].blockSignals(True)
            w_dict["chk_auto"].setChecked(False)
            w_dict["chk_auto"].blockSignals(False)
            self.main_window.settings.setValue(w_dict["setting_key"], False)
            w_dict["disk_lbl"].setText("<font color='grey'><b>[Not Downloaded]</b></font>")
            w_dict["btn_delete"].setEnabled(False)
            w_dict["btn_load"].setText("Download && Load")
        else:
            w_dict["disk_lbl"].setText("<font color='#5cb85c'><b>[Downloaded]</b></font>")
            w_dict["btn_delete"].setEnabled(not is_loading and not is_queued)
            w_dict["btn_load"].setText("Load Model")

        if is_loaded:
            w_dict["status_lbl"].setText("Status: <font color='green'>Loaded in Memory / Ready</font>")
            w_dict["btn_load"].setEnabled(False)
            w_dict["btn_unload"].setEnabled(True)
        elif is_loading:
            w_dict["status_lbl"].setText("Status: <font color='orange'>Downloading / Loading...</font>")
            w_dict["btn_load"].setEnabled(False)
            w_dict["btn_unload"].setEnabled(False)
            w_dict["btn_delete"].setEnabled(False)
        elif is_queued:
            w_dict["status_lbl"].setText("Status: <font color='blue'>Waiting in Queue...</font>")
            w_dict["btn_load"].setEnabled(False)
            w_dict["btn_unload"].setEnabled(False)
            w_dict["btn_delete"].setEnabled(False)
        else:
            w_dict["status_lbl"].setText("Status: <font color='red'>Not Loaded</font>")
            w_dict["btn_load"].setEnabled(True)
            w_dict["btn_unload"].setEnabled(False)

    def update_ui_state(self):
        try:
            q = self.main_window.model_load_queue

            mocr_loaded = self.main_window.mocr_model is not None
            mocr_loading = self.main_window.mocr_is_loading
            mocr_queued = "manga_ocr" in q
            self._apply_state(mocr_loaded, mocr_loading, mocr_queued, self.model_widgets["manga_ocr"])

            yolo_loaded = self.main_window.yolo_model is not None
            yolo_loading = self.main_window.yolo_is_loading
            yolo_queued = "yolo_detector" in q
            self._apply_state(yolo_loaded, yolo_loading, yolo_queued, self.model_widgets["yolo_detector"])

            nmt_loaded = self.main_window.nmt_model is not None
            nmt_loading = self.main_window.nmt_is_loading
            nmt_queued = "nmt_translator" in q
            self._apply_state(nmt_loaded, nmt_loading, nmt_queued, self.model_widgets["nmt_translator"])
        except RuntimeError:
            pass
