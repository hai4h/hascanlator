import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QMessageBox, QStyle
from PySide6.QtCore import Qt, QThread, Signal

class HfCacheDeleteWorker(QThread):
    """Deletes an HF model cache entry off the UI thread (multi-GB operations)."""
    finished_ok = Signal(bool, str)

    def __init__(self, repo_id, cache_dir, parent=None):
        super().__init__(parent)
        self.repo_id = repo_id
        self.cache_dir = cache_dir

    def run(self):
        try:
            from huggingface_hub import scan_cache_dir
            hf_cache_info = scan_cache_dir(self.cache_dir)
            for repo in hf_cache_info.repos:
                if repo.repo_id == self.repo_id:
                    strategy = hf_cache_info.delete_revisions(
                        *[rev.commit_hash for rev in repo.revisions]
                    )
                    strategy.execute()
                    self.finished_ok.emit(True, "")
                    return
            self.finished_ok.emit(False, "Model was not found in the local cache.")
        except Exception as e:
            self.finished_ok.emit(False, str(e))

class ModelManagerWidget(QWidget):
    """Encapsulates the UI and logic for managing a single AI model."""
    def __init__(self, main_window, meta):
        super().__init__()
        self.main_window = main_window
        self.meta = meta
        self.load_key = meta["key"]
        self.repo_getter = meta["repo"] if callable(meta["repo"]) else lambda: meta["repo"]
        self.setting_key = meta["setting"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"<b>{meta['title']}</b><br>{meta['desc']}"))
        self.disk_lbl = QLabel()
        header_layout.addWidget(self.disk_lbl, alignment=Qt.AlignRight | Qt.AlignTop)
        self.btn_info = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation), "")
        if self.btn_info.icon().isNull():
            self.btn_info.setText("\u24d8")
        self.btn_info.setFixedSize(24, 24)
        self.btn_info.setToolTip("Show size, source and inference provider info")
        self.btn_info.clicked.connect(self._open_info)
        header_layout.addWidget(self.btn_info, alignment=Qt.AlignRight | Qt.AlignTop)
        layout.addLayout(header_layout)

        self.status_lbl = QLabel()
        layout.addWidget(self.status_lbl)

        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton("Load Model")
        self.btn_load.clicked.connect(lambda: self.main_window.load_model(self.load_key))

        self.btn_unload = QPushButton("Unload (Free RAM)")
        self.btn_unload.clicked.connect(lambda: self.main_window.unload_model(self.load_key))

        self.btn_delete = QPushButton("Delete from Disk")
        self.btn_delete.setStyleSheet("color: #d9534f;")
        self.btn_delete.clicked.connect(self._delete_model)

        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_unload)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.chk_auto = QCheckBox("Auto-load on next launch")
        self.chk_auto.setChecked(self.main_window.settings.value(self.setting_key, False, type=bool))
        self.chk_auto.stateChanged.connect(lambda: self.main_window.settings.setValue(self.setting_key, self.chk_auto.isChecked()))
        layout.addWidget(self.chk_auto)

    def _open_info(self):
        from src.ui.settings.model_info import ModelInfoDialog
        meta = dict(self.meta)
        meta["repo"] = self.repo_getter()
        ModelInfoDialog(self.main_window, meta).exec()

    def _delete_model(self):
        repo_id = self.repo_getter()
        reply = QMessageBox.question(self, "Confirm Deletion", "Are you sure you want to delete this model from your disk? You will need to redownload it next time.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.main_window.unload_model(self.load_key)
            self.main_window._invalidate_model_cache()
            try:
                if repo_id == "local_masking":
                    if os.path.exists("./models/comictextdetector.pt.onnx"):
                        os.remove("./models/comictextdetector.pt.onnx")
                    QMessageBox.information(self, "Success", "Model successfully deleted from disk.")
                    self.main_window.model_status_changed.emit()
                elif repo_id == "local_inpaint":
                    if os.path.exists("./models/lama_fp32.onnx"):
                        os.remove("./models/lama_fp32.onnx")
                    QMessageBox.information(self, "Success", "Model successfully deleted from disk.")
                    self.main_window.model_status_changed.emit()
                else:
                    cache_dir = os.path.abspath(os.path.join(os.getcwd(), "models", "hf_cache"))
                    if not os.path.exists(cache_dir):
                        QMessageBox.warning(self, "Delete Failed", "Model was not found in the local cache.")
                        self.main_window.model_status_changed.emit()
                        return
                    self.btn_delete.setEnabled(False)
                    self.btn_load.setEnabled(False)
                    self.btn_unload.setEnabled(False)
                    self.status_lbl.setText("Status: <font color='orange'>Deleting from disk...</font>")
                    self._delete_worker = HfCacheDeleteWorker(repo_id, cache_dir)
                    self._delete_worker.finished_ok.connect(self._on_delete_finished)
                    self._delete_worker.start()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete model cache: {e}")

    def _on_delete_finished(self, success, msg):
        self._delete_worker = None
        self.main_window._invalidate_model_cache()
        self.main_window.model_status_changed.emit()
        if success:
            QMessageBox.information(self, "Success", "Model successfully deleted from disk.")
        else:
            QMessageBox.warning(self, "Delete Failed", msg or "Could not delete model cache.")

    def update_state(self):
        is_loaded = False
        is_loading = False
        is_queued = self.load_key in self.main_window.model_load_queue

        if self.load_key == "manga_ocr":
            is_loaded = self.main_window.mocr_model is not None
            is_loading = self.main_window.mocr_is_loading
        elif self.load_key == "yolo_detector":
            is_loaded = self.main_window.yolo_model is not None
            is_loading = self.main_window.yolo_is_loading
        elif self.load_key == "nmt_translator":
            is_loaded = self.main_window.nmt_model is not None
            is_loading = self.main_window.nmt_is_loading
        elif self.load_key == "masking_model":
            is_loaded = self.main_window.masking_model is not None
            is_loading = self.main_window.masking_is_loading
        elif self.load_key == "inpaint_model":
            is_loaded = self.main_window.inpaint_model is not None
            is_loading = self.main_window.inpaint_is_loading

        is_downloaded = self.main_window.is_model_downloaded(self.repo_getter())

        self.chk_auto.setEnabled(is_downloaded)
        if not is_downloaded:
            self.chk_auto.blockSignals(True)
            self.chk_auto.setChecked(False)
            self.chk_auto.blockSignals(False)
            if self.main_window.settings.value(self.setting_key, False):
                self.main_window.settings.setValue(self.setting_key, False)
            self.disk_lbl.setText("<font color='grey'><b>[Not Downloaded]</b></font>")
            self.btn_delete.setEnabled(False)
            self.btn_load.setText("Download && Load")
        else:
            self.disk_lbl.setText("<font color='#5cb85c'><b>[Downloaded]</b></font>")
            self.btn_delete.setEnabled(not is_loading and not is_queued)
            self.btn_load.setText("Load Model")

        if is_loaded:
            self.status_lbl.setText("Status: <font color='green'>Loaded in Memory / Ready</font>")
            self.btn_load.setEnabled(False)
            self.btn_unload.setEnabled(True)
        elif is_loading:
            self.status_lbl.setText("Status: <font color='orange'>Downloading / Loading...</font>")
            self.btn_load.setEnabled(False)
            self.btn_unload.setEnabled(False)
            self.btn_delete.setEnabled(False)
        elif is_queued:
            self.status_lbl.setText("Status: <font color='blue'>Waiting in Queue...</font>")
            self.btn_load.setEnabled(False)
            self.btn_unload.setEnabled(False)
            self.btn_delete.setEnabled(False)
        else:
            self.status_lbl.setText("Status: <font color='red'>Not Loaded</font>")
            self.btn_load.setEnabled(True)
            self.btn_unload.setEnabled(False)


class ModelsTab(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.model_widgets = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.chk_mirror = QCheckBox("Use HuggingFace Mirror (hf-mirror.com) to bypass network restrictions")
        self.chk_mirror.setChecked(self.main_window.settings.value("use_hf_mirror", False, type=bool))
        self.chk_mirror.stateChanged.connect(self._on_mirror_changed)
        layout.addWidget(self.chk_mirror)

        global_btns_layout = QHBoxLayout()

        self.btn_download_all = QPushButton("Download Available")
        self.btn_download_all.setStyleSheet("font-weight: bold; padding: 8px;")
        self.btn_download_all.clicked.connect(self.download_all_missing_models)

        btn_load_all = QPushButton("Load All Available")
        btn_load_all.setStyleSheet("font-weight: bold; padding: 8px;")
        btn_load_all.clicked.connect(self.load_all_models)

        btn_unload_all = QPushButton("Unload All")
        btn_unload_all.setStyleSheet("font-weight: bold; padding: 8px;")
        btn_unload_all.clicked.connect(self.unload_all_models)

        global_btns_layout.addWidget(self.btn_download_all)
        global_btns_layout.addWidget(btn_load_all)
        global_btns_layout.addWidget(btn_unload_all)

        layout.addLayout(global_btns_layout)
        layout.addWidget(QLabel("<hr>"))

        models = [
            {"title": "MangaOCR (Text Recognition)", "desc": "Reads Japanese text inside the boxes.", "key": "manga_ocr", "repo": "kha-white/manga-ocr-base", "setting": "auto_load_mocr", "kind": "torch", "source": "https://huggingface.co/kha-white/manga-ocr-base"},
            {"title": "YOLOv8 Bubble Detector", "desc": "Accurate speech bubble locator.", "key": "yolo_detector", "repo": "ogkalu/manga-text-detector-yolov8s", "setting": "auto_load_yolo", "kind": "torch", "source": "https://huggingface.co/ogkalu/manga-text-detector-yolov8s"},
            {"title": "Text Masking Model (comictextdetector)", "desc": "Accurately masks text before inpainting.", "key": "masking_model", "repo": "local_masking", "setting": "auto_load_masking", "kind": "onnx", "source": "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt.onnx", "local_path": "./models/comictextdetector.pt.onnx"},
            {"title": "Image Inpainting Model (LaMa)", "desc": "Seamlessly removes text using masks.", "key": "inpaint_model", "repo": "local_inpaint", "setting": "auto_load_inpaint", "kind": "onnx", "source": "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx", "local_path": "./models/lama_fp32.onnx"},
        ]

        for i, m in enumerate(models):
            widget = ModelManagerWidget(self.main_window, m)
            layout.addWidget(widget)
            self.model_widgets.append(widget)
            if i < len(models) - 1:
                layout.addWidget(QLabel("<hr>"))

        layout.addStretch()

    def _on_mirror_changed(self, state):
        is_checked = state == 2
        self.main_window.settings.setValue("use_hf_mirror", is_checked)
        if is_checked:
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        else:
            os.environ.pop("HF_ENDPOINT", None)

    def download_all_missing_models(self):
        for w in self.model_widgets:
            if not self.main_window.is_model_downloaded(w.repo_getter()):
                if w.load_key not in self.main_window.model_load_queue:
                    self.main_window.load_model(w.load_key)

    def load_all_models(self):
        for w in self.model_widgets:
            if self.main_window.is_model_downloaded(w.repo_getter()):
                if w.load_key not in self.main_window.model_load_queue:
                    self.main_window.load_model(w.load_key)

    def unload_all_models(self):
        for w in self.model_widgets:
            self.main_window.unload_model(w.load_key)

    def update_ui_state(self):
        for w in self.model_widgets:
            w.update_state()

        all_downloaded = True
        for w in self.model_widgets:
            if not self.main_window.is_model_downloaded(w.repo_getter()):
                all_downloaded = False
                break
        self.btn_download_all.setEnabled(not all_downloaded)