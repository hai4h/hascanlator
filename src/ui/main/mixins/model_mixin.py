import gc
from PySide6.QtWidgets import QMessageBox
from src.core.loader_worker import ModelLoaderWorker

class ModelManagementMixin:
    # --- MODEL LOADING LOGIC ---
    def load_model(self, model_name):
        if model_name not in self.model_load_queue:
            self.model_load_queue.append(model_name)
            self.model_status_changed.emit()
        self._process_model_queue()

    def _process_model_queue(self):
        if self.is_loading_model_seq or not self.model_load_queue: return
            
        model_name = self.model_load_queue.pop(0)
        self.is_loading_model_seq = True

        if model_name == "manga_ocr": self.mocr_is_loading = True
        elif model_name == "yolo_detector": self.yolo_is_loading = True
        elif model_name == "nmt_translator": self.nmt_is_loading = True
            
        self.update_window_title()
        self.model_status_changed.emit()
        self.update_button_states()
        
        loader = ModelLoaderWorker(model_name)
        self.loader_threads.append(loader)
        loader.finished.connect(lambda m, n, t=loader: self.on_model_loaded(m, n, t))
        loader.error.connect(lambda n, e, t=loader: self.on_model_error(n, e, t))
        loader.start()

    def on_model_loaded(self, model, name, thread_ref):
        if name == "manga_ocr":
            self.mocr_model, self.mocr_is_loading = model, False
        elif name == "yolo_detector":
            self.yolo_model, self.yolo_is_loading = model, False
        elif name == "nmt_translator":
            self.nmt_model, self.nmt_is_loading = model, False

        if thread_ref in self.loader_threads: self.loader_threads.remove(thread_ref)
            
        self.is_loading_model_seq = False
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit() 
        self._process_model_queue() 

    def on_model_error(self, name, err, thread_ref):
        QMessageBox.critical(self, "Model Load Error", f"Failed to load {name}:\n{err}")
        if name == "manga_ocr": self.mocr_is_loading = False
        elif name == "yolo_detector": self.yolo_is_loading = False
        elif name == "nmt_translator": self.nmt_is_loading = False
            
        if thread_ref in self.loader_threads: self.loader_threads.remove(thread_ref)
            
        self.is_loading_model_seq = False
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit()
        self._process_model_queue() 

    def unload_model(self, model_name):
        if model_name == "manga_ocr": self.mocr_model = None
        elif model_name == "yolo_detector": self.yolo_model = None
        elif model_name == "nmt_translator": self.nmt_model = None
            
        gc.collect() 
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit()