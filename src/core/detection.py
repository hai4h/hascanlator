from PySide6.QtCore import QThread, Signal, QRectF

class DetectionWorker(QThread):
    process_finished = Signal(list)
    error = Signal(str)

    def __init__(self, image_path, yolo_model):
        super().__init__()
        self.image_path = image_path
        self.yolo_model = yolo_model

    def run(self):
        try:
            if not self.yolo_model:
                raise RuntimeError("Model not loaded.")

            results = self.yolo_model.predict(self.image_path, conf=0.25, verbose=False)
            boxes = []
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    pad = 5
                    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
                    w, h = (x2 - x1) + (pad * 2), (y2 - y1) + (pad * 2)
                    boxes.append(QRectF(x1, y1, w, h))
            self.process_finished.emit(boxes)
        except Exception as e:
            self.error.emit(str(e))
