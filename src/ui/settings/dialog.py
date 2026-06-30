from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton, QTabWidget, QCheckBox

class SettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Settings & Model Manager")
        self.resize(550, 450)
        
        self.main_window.model_status_changed.connect(self.update_ui_state)
        
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        models_tab = QWidget()
        self.models_layout = QVBoxLayout(models_tab)
        
        # Helper function to generate standardized UI for each model
        def add_model_ui(title, desc, load_key):
            model_layout = QVBoxLayout()
            model_layout.addWidget(QLabel(f"<b>{title}</b><br>{desc}"))
            
            status_lbl = QLabel()
            model_layout.addWidget(status_lbl)
            
            btn_layout = QHBoxLayout()
            btn_load = QPushButton("Load Model")
            btn_load.clicked.connect(lambda: self.main_window.load_model(load_key))
            
            btn_unload = QPushButton("Unload (Free Memory)")
            btn_unload.clicked.connect(lambda: self.main_window.unload_model(load_key))
            
            btn_layout.addWidget(btn_load)
            btn_layout.addWidget(btn_unload)
            model_layout.addLayout(btn_layout)
            
            chk_auto = QCheckBox("Auto-load on next launch")
            setting_key = f"auto_load_{load_key.split('_')[0]}"
            chk_auto.setChecked(self.main_window.settings.value(setting_key, False, type=bool))
            chk_auto.stateChanged.connect(lambda state, key=setting_key, chk=chk_auto: 
                                          self.main_window.settings.setValue(key, chk.isChecked()))
            model_layout.addWidget(chk_auto)
            
            model_layout.addWidget(QLabel("<hr>"))
            self.models_layout.addLayout(model_layout)
            
            return status_lbl, btn_load, btn_unload

        # Generate UI for all 3 models
        self.lbl_mocr, self.btn_load_mocr, self.btn_unload_mocr = add_model_ui(
            "MangaOCR (Text Recognition)", "Reads Japanese text inside the boxes.", "manga_ocr"
        )
        self.lbl_yolo, self.btn_load_yolo, self.btn_unload_yolo = add_model_ui(
            "YOLOv8 Bubble Detector", "Machine learning-based accurate speech bubble locator.", "yolo_detector"
        )
        self.lbl_nmt, self.btn_load_nmt, self.btn_unload_nmt = add_model_ui(
            "NMT Translator (JA to EN)", "Translates recognized Japanese text into English.", "nmt_translator"
        )
        
        self.models_layout.addStretch()
        tabs.addTab(models_tab, "Models")
        layout.addWidget(tabs)
        
        self.update_ui_state() 

    def _apply_state(self, is_loaded, is_loading, is_queued, lbl, btn_load, btn_unload):
        if is_loaded:
            lbl.setText("Status: <font color='green'>Loaded in Memory / Ready</font>")
            btn_load.setEnabled(False)
            btn_unload.setEnabled(True)
        elif is_loading:
            lbl.setText("Status: <font color='orange'>Downloading / Loading... (Check terminal)</font>")
            btn_load.setEnabled(False)
            btn_unload.setEnabled(False)
        elif is_queued:
            lbl.setText("Status: <font color='blue'>Waiting in Queue...</font>")
            btn_load.setEnabled(False)
            btn_unload.setEnabled(False)
        else:
            lbl.setText("Status: <font color='red'>Not Loaded</font>")
            btn_load.setEnabled(True)
            btn_unload.setEnabled(False)

    def update_ui_state(self):
        q = self.main_window.model_load_queue
        
        mocr_loaded = self.main_window.mocr_model is not None
        mocr_loading = self.main_window.mocr_is_loading
        mocr_queued = "manga_ocr" in q
        self._apply_state(mocr_loaded, mocr_loading, mocr_queued, self.lbl_mocr, self.btn_load_mocr, self.btn_unload_mocr)
        
        yolo_loaded = self.main_window.yolo_model is not None
        yolo_loading = self.main_window.yolo_is_loading
        yolo_queued = "yolo_detector" in q
        self._apply_state(yolo_loaded, yolo_loading, yolo_queued, self.lbl_yolo, self.btn_load_yolo, self.btn_unload_yolo)

        nmt_loaded = self.main_window.nmt_model is not None
        nmt_loading = self.main_window.nmt_is_loading
        nmt_queued = "nmt_translator" in q
        self._apply_state(nmt_loaded, nmt_loading, nmt_queued, self.lbl_nmt, self.btn_load_nmt, self.btn_unload_nmt)