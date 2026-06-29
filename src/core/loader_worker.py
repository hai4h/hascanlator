from PySide6.QtCore import QThread, Signal

class ModelLoaderWorker(QThread):
    finished = Signal(object, str) 
    error = Signal(str, str)

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            if self.model_name == "manga_ocr":
                from manga_ocr import MangaOcr
                model = MangaOcr() 
                self.finished.emit(model, self.model_name)
                
            elif self.model_name == "yolo_detector":
                from ultralytics import YOLO
                from huggingface_hub import hf_hub_download
                model_path = hf_hub_download(repo_id="ogkalu/manga-text-detector-yolov8s", filename="manga-text-detector.pt")
                model = YOLO(model_path)
                self.finished.emit(model, self.model_name)
                
        except Exception as e:
            self.error.emit(self.model_name, str(e))