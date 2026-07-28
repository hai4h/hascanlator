from PySide6.QtCore import QThread, Signal

class ModelLoaderWorker(QThread):
    process_finished = Signal(object, str)
    error = Signal(str, str)

    def __init__(self, model_name, nmt_repo_id="Helsinki-NLP/opus-mt-ja-en"):
        super().__init__()
        self.model_name = model_name
        self.nmt_repo_id = nmt_repo_id

    def run(self):
        try:
            if self.model_name == "manga_ocr":
                from huggingface_hub import snapshot_download
                try:
                    model_path = snapshot_download(repo_id="kha-white/manga-ocr-base", token=False)
                except Exception as dl_err:
                    raise RuntimeError(f"Could not download model. If you have network restrictions, enable 'HuggingFace Mirror' in Settings.\n\nError: {dl_err}")

                from manga_ocr import MangaOcr
                model = MangaOcr(pretrained_model_name_or_path=model_path)
                self.process_finished.emit(model, self.model_name)

            elif self.model_name == "yolo_detector":
                from ultralytics import YOLO
                from huggingface_hub import hf_hub_download
                try:
                    model_path = hf_hub_download(repo_id="ogkalu/manga-text-detector-yolov8s", filename="manga-text-detector.pt", token=False)
                except Exception as dl_err:
                    raise RuntimeError(f"Could not download model. If you have network restrictions, enable 'HuggingFace Mirror' in Settings.\n\nError: {dl_err}")

                model = YOLO(model_path)
                self.process_finished.emit(model, self.model_name)

            elif self.model_name == "nmt_translator":
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                from huggingface_hub import snapshot_download

                repo_id = self.nmt_repo_id
                try:
                    model_path = snapshot_download(repo_id=repo_id, token=False)
                except Exception as dl_err:
                    raise RuntimeError(f"Could not download model. If you have network restrictions, enable 'HuggingFace Mirror' in Settings.\n\nError: {dl_err}")

                tokenizer = AutoTokenizer.from_pretrained(model_path)
                model = AutoModelForSeq2SeqLM.from_pretrained(model_path)

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

                self.process_finished.emit(NMTWrapper(tokenizer, model, repo_id), self.model_name)

            elif self.model_name == "masking_model":
                import os
                import sys
                
                model_path = "./models/comictextdetector.pt"
                repo_path = os.path.abspath("./comic_text_detector")
                
                if not os.path.exists(repo_path):
                    raise RuntimeError("Testing Mode: 'comic_text_detector' folder not found. Please run 'git clone https://github.com/dmMaze/comic-text-detector.git comic_text_detector' in your terminal.")

                if not os.path.exists(model_path):
                    raise RuntimeError(f"Testing Mode: Model not found at {model_path}. Please place 'comictextdetector.pt' inside the /models directory.")
                
                # Add the repository to the Python path so its internal flat imports work natively
                if repo_path not in sys.path:
                    sys.path.insert(0, repo_path)

                class ComicTextDetectorWrapper:
                    def __init__(self, path):
                        self.path = path
                        try:
                            from inference import TextDetector
                            self.model = TextDetector(model_path=path, device='cpu', act='leaky')
                        except Exception as e:
                            self.model = None
                            print(f"comic_text_detector module error: {e}. Falling back to OpenCV thresholding.")

                    def __call__(self, img_crop):
                        if self.model is None:
                            import cv2
                            gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
                            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                            return binary
                            
                        try:
                            result = self.model(img_crop)
                            return result[0]
                        except Exception as e:
                            print(f"Masking inference error: {e}")
                            import numpy as np
                            return np.zeros(img_crop.shape[:2], dtype=np.uint8)
                
                model = ComicTextDetectorWrapper(model_path)
                self.process_finished.emit(model, self.model_name)

            elif self.model_name == "inpaint_model":
                import os
                model_path = "./models/inpainting_lama_mpe.ckpt"
                
                if not os.path.exists(model_path):
                    raise RuntimeError(f"Testing Mode: Model not found at {model_path}. Please place 'inpainting_lama_mpe.ckpt' inside the /models directory.")
                
                class LamaInpainterWrapper:
                    def __init__(self, path):
                        self.path = path
                        # Hook for manga-image-translator's LaMa inpainter module here
                        
                    def __call__(self, img_crop, mask):
                        import cv2
                        import numpy as np
                        # If Lama is not fully connected in Python yet, cv2.inpaint is used as a placeholder 
                        # so you can verify the pipeline end-to-end
                        mask_np = mask.astype(np.uint8)
                        inpainted = cv2.inpaint(img_crop, mask_np, 7, cv2.INPAINT_TELEA)
                        return inpainted
                        
                model = LamaInpainterWrapper(model_path)
                self.process_finished.emit(model, self.model_name)

        except Exception as e:
            self.error.emit(self.model_name, str(e))
