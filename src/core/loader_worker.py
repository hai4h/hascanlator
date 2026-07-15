from PySide6.QtCore import QThread, Signal

class ModelLoaderWorker(QThread):
    finished = Signal(object, str) 
    error = Signal(str, str)

    def __init__(self, model_name, nmt_repo_id="Helsinki-NLP/opus-mt-ja-en"):
        super().__init__()
        self.model_name = model_name
        self.nmt_repo_id = nmt_repo_id

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
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                
                # Use passed repo_id instead of reading config here
                repo_id = self.nmt_repo_id 
                tokenizer = AutoTokenizer.from_pretrained(repo_id)
                model = AutoModelForSeq2SeqLM.from_pretrained(repo_id)
                
                class NMTWrapper:
                    def __init__(self, tok, mod, repo):
                        self.tokenizer = tok
                        self.model = mod
                        self.repo = repo
                        
                    def __call__(self, text, src_lang="ja", tgt_lang="en"):
                        if "nllb" in self.repo:
                            lang_map = {
                                "auto": "jpn_Jpan", "ja": "jpn_Jpan", "en": "eng_Latn", 
                                "ko": "kor_Hang", "zh-CN": "zho_Hans", "vi": "vie_Latn", 
                                "es": "spa_Latn", "fr": "fra_Latn"
                            }
                            self.tokenizer.src_lang = lang_map.get(src_lang, "jpn_Jpan")
                            inputs = self.tokenizer(text, return_tensors="pt", padding=True)
                            
                            target_code = lang_map.get(tgt_lang, "eng_Latn")
                            
                            if hasattr(self.tokenizer, "lang_code_to_id"):
                                forced_bos_token_id = self.tokenizer.lang_code_to_id[target_code]
                            else:
                                forced_bos_token_id = self.tokenizer.convert_tokens_to_ids(target_code)
                            
                            translated_tokens = self.model.generate(
                                **inputs, 
                                forced_bos_token_id=forced_bos_token_id
                            )
                        else:
                            inputs = self.tokenizer(text, return_tensors="pt", padding=True)
                            translated_tokens = self.model.generate(**inputs)
                            
                        res_text = self.tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
                        return [{"translation_text": res_text}]
                        
                self.finished.emit(NMTWrapper(tokenizer, model, repo_id), self.model_name)
                
        except Exception as e:
            self.error.emit(self.model_name, str(e))