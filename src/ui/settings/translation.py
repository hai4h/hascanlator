from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QStackedWidget, QCheckBox
from PySide6.QtCore import Qt
from src.ui.settings.models import ModelManagerWidget

class TranslationTab(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.nmt_widget = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        engine_layout = QHBoxLayout()
        engine_layout.addWidget(QLabel("<b>Translation Method:</b>"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Online API", "Local Offline NMT"])

        current_engine = self.main_window.settings.value("translation_engine", "google")
        self.engine_combo.setCurrentIndex(0 if current_engine == "google" else 1)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)

        engine_layout.addWidget(self.engine_combo)
        layout.addLayout(engine_layout)
        layout.addWidget(QLabel("<hr>"))

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
        
        self.nmt_widget = ModelManagerWidget(self.main_window, {
            "title": "NMT Engine",
            "desc": "Processes translation locally on your device.",
            "key": "nmt_translator",
            "repo": lambda: self.main_window.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en"),
            "setting": "auto_load_nmt",
            "kind": "torch",
            "source": "https://huggingface.co/{repo}",
        })
        nmt_layout.addWidget(self.nmt_widget)
        nmt_layout.addStretch()
        self.trans_stack.addWidget(nmt_page)

        layout.addWidget(self.trans_stack)
        self.trans_stack.setCurrentIndex(0 if current_engine == "google" else 1)

        self._update_nmt_lang_states()

        layout.addWidget(QLabel("<hr>"))
        layout.addWidget(QLabel("<b>Text Formatting & Editor</b>"))

        chk_ocr_edit = QCheckBox("Allow manual editing of OCR text box")
        chk_ocr_edit.setChecked(self.main_window.settings.value("ocr_allow_edit", False, type=bool))

        def on_ocr_edit_changed(v):
            self.main_window.settings.setValue("ocr_allow_edit", v)
            self.main_window.right_dock.ocr_input.setReadOnly(not v)

        chk_ocr_edit.stateChanged.connect(lambda: on_ocr_edit_changed(chk_ocr_edit.isChecked()))
        layout.addWidget(chk_ocr_edit)

        chk_ell_std = QCheckBox("Auto-convert Japanese ellipsis to standard '...' (Post-translation)")
        chk_ell_std.setChecked(self.main_window.settings.value("format_ellipsis_standard", True, type=bool))
        chk_ell_std.stateChanged.connect(lambda: self.main_window.settings.setValue("format_ellipsis_standard", chk_ell_std.isChecked()))
        layout.addWidget(chk_ell_std)

        chk_ell_nl = QCheckBox("Auto-move ellipsis to a separate line (Post-translation)")
        chk_ell_nl.setChecked(self.main_window.settings.value("format_ellipsis_newline", True, type=bool))
        chk_ell_nl.stateChanged.connect(lambda: self.main_window.settings.setValue("format_ellipsis_newline", chk_ell_nl.isChecked()))
        layout.addWidget(chk_ell_nl)

        layout.addStretch()

    def _on_engine_changed(self, index):
        engine = "google" if index == 0 else "nmt"
        self.main_window.settings.setValue("translation_engine", engine)
        self.trans_stack.setCurrentIndex(index)

        if engine == "google":
            if self.main_window.nmt_model is not None or self.main_window.nmt_is_loading:
                self.main_window.unload_model("nmt_translator")

        self.main_window.update_button_states()
        self.main_window.model_status_changed.emit()

    def _on_nmt_repo_changed(self, index):
        new_repo = "facebook/nllb-200-distilled-600M" if index == 1 else "Helsinki-NLP/opus-mt-ja-en"
        old_repo = self.main_window.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en")
        if new_repo != old_repo:
            self.main_window.settings.setValue("nmt_model_repo", new_repo)
            self._update_nmt_lang_states()

            if self.main_window.nmt_model is not None or self.main_window.nmt_is_loading:
                self.main_window.unload_model("nmt_translator")

            self.main_window.model_status_changed.emit()

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

    def update_ui_state(self):
        if self.nmt_widget:
            self.nmt_widget.update_state()