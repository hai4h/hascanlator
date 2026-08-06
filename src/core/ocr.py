from PIL import Image
from PySide6.QtCore import QThread, Signal

class BatchOCRWorker(QThread):
    progress = Signal(str, object)
    progress_percent = Signal(int)
    process_finished = Signal()
    error = Signal(str)

    def __init__(self, mocr_model, image_path, boxes_data):
        super().__init__()
        self.mocr = mocr_model
        self.image_path = image_path
        self.boxes_data = boxes_data

    def run(self):
        img = None
        try:
            img = Image.open(self.image_path)
            total = len(self.boxes_data)

            for i, (rect, box_ref) in enumerate(self.boxes_data):
                x, y, w, h = rect
                x, y = max(0, x), max(0, y)
                text = self.mocr(img.crop((x, y, x + w, y + h)))

                self.progress.emit(text, box_ref)
                self.progress_percent.emit(int(((i + 1) / total) * 100))

            self.process_finished.emit()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass
