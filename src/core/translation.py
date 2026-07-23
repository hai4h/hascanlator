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
                    if self.engine == "google":
                        translated_text = translator.translate(text)
                    else:
                        # Local NMT (Helsinki-NLP/opus-mt-ja-en) is fixed to Japanese -> English
                        result = self.nmt_model(text)
                        translated_text = result[0]['translation_text']
                        
                    self.progress.emit(translated_text, box_ref)
                
                self.progress_percent.emit(int(((i + 1) / total) * 100))
                
            self.process_finished.emit()
        except Exception as e:
            self.error.emit(str(e))