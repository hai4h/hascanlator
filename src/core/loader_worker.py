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

            elif self.model_name == "nmt_translator":
                from transformers import MarianMTModel, MarianTokenizer
                
                model_id = "Helsinki-NLP/opus-mt-ja-en"
                tokenizer = MarianTokenizer.from_pretrained(model_id)
                model = MarianMTModel.from_pretrained(model_id)
                
                # Create a simple wrapper to keep compatibility with our BatchTranslationWorker
                class NMTWrapper:
                    def __init__(self, tok, mod):
                        self.tokenizer = tok
                        self.model = mod
                        
                    def __call__(self, text):
                        inputs = self.tokenizer(text, return_tensors="pt", padding=True)
                        translated_tokens = self.model.generate(**inputs)
                        res_text = self.tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
                        return [{"translation_text": res_text}]
                        
                self.finished.emit(NMTWrapper(tokenizer, model), self.model_name)
                
        except Exception as e:
            self.error.emit(self.model_name, str(e))