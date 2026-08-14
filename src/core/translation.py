from PySide6.QtCore import QThread, Signal

class BatchTranslationWorker(QThread):
    progress = Signal(str, object) 
    progress_percent = Signal(int)
    process_finished = Signal()
    error = Signal(str)

    def __init__(self, engine, nmt_model, boxes_data, source_lang='ja', target_lang='en'):
        super().__init__()
        self.engine = engine
        self.nmt_model = nmt_model
        self.boxes_data = boxes_data 
        self.source_lang = source_lang
        self.target_lang = target_lang

    def run(self):
        try:
            total = len(self.boxes_data)
            translator = None
            
            # Instantiate online translator with user-selected languages if selected
            if self.engine == "google":
                from deep_translator import GoogleTranslator
                translator = GoogleTranslator(source=self.source_lang, target=self.target_lang)
                
                for i, (text, box_ref) in enumerate(self.boxes_data):
                    if not text or not text.strip():
                        self.progress.emit("", box_ref)
                    else:
                        self.progress.emit(translator.translate(text), box_ref)
                    self.progress_percent.emit(int(((i + 1) / total) * 100))
            else:
                # Local NMT: batch all non-empty texts into a single generate call.
                # Skip empty entries so the model is never fed padding-only rows.
                to_translate = [
                    (text, box_ref)
                    for text, box_ref in self.boxes_data
                    if text and text.strip()
                ]
                results = []
                if to_translate:
                    results = self.nmt_model([t for t, _ in to_translate])

                res_iter = iter(results)
                for i, (text, box_ref) in enumerate(self.boxes_data):
                    if not text or not text.strip():
                        self.progress.emit("", box_ref)
                    else:
                        self.progress.emit(next(res_iter)["translation_text"], box_ref)
                    self.progress_percent.emit(int(((i + 1) / total) * 100))
                
            self.process_finished.emit()
        except Exception as e:
            self.error.emit(str(e))