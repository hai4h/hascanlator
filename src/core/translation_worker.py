from PySide6.QtCore import QThread, Signal

class BatchTranslationWorker(QThread):
    progress = Signal(str, object) 
    progress_percent = Signal(int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, translator_model, boxes_data):
        super().__init__()
        self.translator = translator_model
        self.boxes_data = boxes_data 

    def run(self):
        try:
            total = len(self.boxes_data)
            for i, (text, box_ref) in enumerate(self.boxes_data):
                if not text or not text.strip():
                    self.progress.emit("", box_ref)
                else:
                    result = self.translator(text)
                    translated_text = result[0]['translation_text']
                    self.progress.emit(translated_text, box_ref)
                
                self.progress_percent.emit(int(((i + 1) / total) * 100))
                
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))