from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, 
    QPushButton, QTabWidget, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt
from huggingface_hub import scan_cache_dir

class SettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Settings & Model Manager")
        self.resize(600, 500)
        
        self.main_window.model_status_changed.connect(self.update_ui_state)
        
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        models_tab = QWidget()
        self.models_layout = QVBoxLayout(models_tab)
        
        # --- GLOBAL LOAD / UNLOAD BUTTONS ---
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
        
        # --- HELPER TO BUILD INDIVIDUAL MODEL UI ---
        def add_model_ui(title, desc, load_key, repo_id, setting_key):
            model_layout = QVBoxLayout()
            
            # Header with Title and Disk Indicator
            header_layout = QHBoxLayout()
            header_layout.addWidget(QLabel(f"<b>{title}</b><br>{desc}"))
            
            disk_lbl = QLabel()
            header_layout.addWidget(disk_lbl, alignment=Qt.AlignRight | Qt.AlignTop)
            model_layout.addLayout(header_layout)
            
            status_lbl = QLabel()
            model_layout.addWidget(status_lbl)
            
            # Action Buttons
            btn_layout = QHBoxLayout()
            btn_load = QPushButton("Load Model")
            btn_load.clicked.connect(lambda: self.main_window.load_model(load_key))
            
            btn_unload = QPushButton("Unload (Free RAM)")
            btn_unload.clicked.connect(lambda: self.main_window.unload_model(load_key))
            
            btn_delete = QPushButton("Delete from Disk")
            btn_delete.setStyleSheet("color: #d9534f;")
            btn_delete.clicked.connect(lambda: self.delete_model(load_key, repo_id))
            
            btn_layout.addWidget(btn_load)
            btn_layout.addWidget(btn_unload)
            btn_layout.addWidget(btn_delete)
            model_layout.addLayout(btn_layout)
            
            # Auto-Load Checkbox
            chk_auto = QCheckBox("Auto-load on next launch")
            chk_auto.setChecked(self.main_window.settings.value(setting_key, False, type=bool))
            chk_auto.stateChanged.connect(lambda state, key=setting_key, chk=chk_auto: 
                                          self.main_window.settings.setValue(key, chk.isChecked()))
            model_layout.addWidget(chk_auto)
            
            model_layout.addWidget(QLabel("<hr>"))
            self.models_layout.addLayout(model_layout)
            
            # Store references to widgets to update them dynamically later
            self.model_widgets[load_key] = {
                "status_lbl": status_lbl,
                "disk_lbl": disk_lbl,
                "btn_load": btn_load,
                "btn_unload": btn_unload,
                "btn_delete": btn_delete,
                "chk_auto": chk_auto,
                "setting_key": setting_key,
                "repo_id": repo_id
            }

        # --- BUILD THE LIST WITH EXPLICIT KEYS ---
        add_model_ui("MangaOCR (Text Recognition)", "Reads Japanese text inside the boxes.", "manga_ocr", "kha-white/manga-ocr-base", "auto_load_mocr")
        add_model_ui("YOLOv8 Bubble Detector", "Accurate speech bubble locator.", "yolo_detector", "ogkalu/manga-text-detector-yolov8s", "auto_load_yolo")
        add_model_ui("NMT Translator (JA to EN)", "Translates recognized Japanese text into English.", "nmt_translator", "Helsinki-NLP/opus-mt-ja-en", "auto_load_nmt")
        
        self.models_layout.addStretch()
        tabs.addTab(models_tab, "Models")
        layout.addWidget(tabs)
        
        self.update_ui_state() 

    def load_all_models(self):
        """Iterates through all downloaded models and queues them for loading."""
        for key, w_dict in self.model_widgets.items():
            if not self.is_model_downloaded(w_dict["repo_id"]):
                continue # Skip models that haven't been downloaded yet
                
            if key not in self.main_window.model_load_queue:
                is_loaded = False
                if key == "manga_ocr" and self.main_window.mocr_model: is_loaded = True
                if key == "yolo_detector" and self.main_window.yolo_model: is_loaded = True
                if key == "nmt_translator" and self.main_window.nmt_model: is_loaded = True
                
                if not is_loaded:
                    self.main_window.load_model(key)

    def unload_all_models(self):
        """Iterates through all loaded models and unloads them from memory."""
        for key in self.model_widgets.keys():
            is_loaded = False
            if key == "manga_ocr" and self.main_window.mocr_model: is_loaded = True
            if key == "yolo_detector" and self.main_window.yolo_model: is_loaded = True
            if key == "nmt_translator" and self.main_window.nmt_model: is_loaded = True
            
            if is_loaded:
                self.main_window.unload_model(key)

    def is_model_downloaded(self, repo_id):
        """Scans the HuggingFace cache to see if the model exists on disk."""
        try:
            hf_cache_info = scan_cache_dir()
            for repo in hf_cache_info.repos:
                if repo.repo_id == repo_id:
                    return True
            return False
        except Exception:
            return False

    def delete_model(self, load_key, repo_id):
        """Safely removes the model from both memory and disk."""
        reply = QMessageBox.question(
            self, 
            "Confirm Deletion", 
            "Are you sure you want to delete this model from your disk? You will need to redownload it next time.", 
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.main_window.unload_model(load_key) # Dump from RAM first
            try:
                hf_cache_info = scan_cache_dir()
                for repo in hf_cache_info.repos:
                    if repo.repo_id == repo_id:
                        # Queue deletion of all revisions for this specific repo
                        strategy = hf_cache_info.delete_revisions(*[rev.commit_hash for rev in repo.revisions])
                        strategy.execute()
                        break
                QMessageBox.information(self, "Success", "Model successfully deleted from disk.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete model cache: {e}")
                
            self.update_ui_state()

    def _apply_state(self, is_loaded, is_loading, is_queued, w_dict):
        """Applies button disabling and colors based on the state."""
        # 1. Disk Check (Also manages the Checkbox!)
        is_downloaded = self.is_model_downloaded(w_dict["repo_id"])
        
        w_dict["chk_auto"].setEnabled(is_downloaded)
        if not is_downloaded:
            # Force uncheck the auto-load option and reset settings config to False
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
            
        # 2. RAM & Action Check
        if is_loaded:
            w_dict["status_lbl"].setText("Status: <font color='green'>Loaded in Memory / Ready</font>")
            w_dict["btn_load"].setEnabled(False)
            w_dict["btn_unload"].setEnabled(True)
        elif is_loading:
            w_dict["status_lbl"].setText("Status: <font color='orange'>Downloading / Loading... (Check terminal)</font>")
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
        """Maps specific main_window variables to the UI builder."""
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