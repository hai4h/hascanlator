from PIL import Image
from PySide6.QtCore import QThread, Signal, QRectF
from src.core.detector import TextDetector

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

class BatchOCRWorker(QThread):
    progress = Signal(str, object) 
    finished = Signal()
    error = Signal(str)

    def __init__(self, mocr_model, image_path, boxes_data):
        super().__init__()
        self.mocr = mocr_model
        self.image_path = image_path
        self.boxes_data = boxes_data 

    def run(self):
        try:
            img = Image.open(self.image_path)
            for rect, box_ref in self.boxes_data:
                x, y, w, h = rect
                x, y = max(0, x), max(0, y)
                text = self.mocr(img.crop((x, y, x + w, y + h)))
                self.progress.emit(text, box_ref)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class DetectionWorker(QThread):
    finished = Signal(list)
    error = Signal(str)
    
    def __init__(self, image_path, yolo_model=None):
        super().__init__()
        self.image_path = image_path
        self.yolo_model = yolo_model
        
    def run(self):
        try:
            if self.yolo_model:
                results = self.yolo_model.predict(self.image_path, conf=0.25, verbose=False)
                boxes = []
                for result in results:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        pad = 5
                        x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
                        w, h = (x2 - x1) + (pad * 2), (y2 - y1) + (pad * 2)
                        boxes.append(QRectF(x1, y1, w, h))
                self.finished.emit(boxes)
            else:
                self.finished.emit(TextDetector.detect_text_regions(self.image_path))
        except Exception as e:
            self.error.emit(str(e))