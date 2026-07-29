from PySide6.QtCore import QThread, Signal

class ModelLoaderWorker(QThread):
    process_finished = Signal(object, str)
    error = Signal(str, str)
    progress_percent = Signal(int)

    def __init__(self, model_name, nmt_repo_id="Helsinki-NLP/opus-mt-ja-en"):
        super().__init__()
        self.model_name = model_name
        self.nmt_repo_id = nmt_repo_id
        
    def _download_file(self, url, dest):
        import urllib.request
        import os
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(dest, 'wb') as out_file:
            total_length = response.info().get('Content-Length')
            if total_length:
                total_length = int(total_length)
                read_so_far = 0
                chunk_size = max(4096, total_length // 100)
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    read_so_far += len(chunk)
                    percent = int((read_so_far * 100) / total_length)
                    self.progress_percent.emit(min(100, percent))
            else:
                out_file.write(response.read())

    def run(self):
        try:
            if self.model_name == "manga_ocr":
                import os
                from huggingface_hub import snapshot_download
                try:
                    cache_dir = os.path.abspath(os.path.join(os.getcwd(), "models", "hf_cache"))
                    model_path = snapshot_download(repo_id="kha-white/manga-ocr-base", token=False, cache_dir=cache_dir)
                except Exception as dl_err:
                    raise RuntimeError(f"Could not download model. If you have network restrictions, enable 'HuggingFace Mirror' in Settings.\n\nError: {dl_err}")

                from manga_ocr import MangaOcr
                model = MangaOcr(pretrained_model_name_or_path=model_path)
                self.process_finished.emit(model, self.model_name)

            elif self.model_name == "yolo_detector":
                import os
                from ultralytics import YOLO
                from huggingface_hub import hf_hub_download
                try:
                    cache_dir = os.path.abspath(os.path.join(os.getcwd(), "models", "hf_cache"))
                    model_path = hf_hub_download(repo_id="ogkalu/manga-text-detector-yolov8s", filename="manga-text-detector.pt", token=False, cache_dir=cache_dir)
                except Exception as dl_err:
                    raise RuntimeError(f"Could not download model. If you have network restrictions, enable 'HuggingFace Mirror' in Settings.\n\nError: {dl_err}")

                model = YOLO(model_path)
                self.process_finished.emit(model, self.model_name)

            elif self.model_name == "nmt_translator":
                import os
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                from huggingface_hub import snapshot_download

                repo_id = self.nmt_repo_id
                try:
                    cache_dir = os.path.abspath(os.path.join(os.getcwd(), "models", "hf_cache"))
                    model_path = snapshot_download(repo_id=repo_id, token=False, cache_dir=cache_dir)
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
                model_path = "./models/comictextdetector.pt.onnx"

                if not os.path.exists(model_path):
                    self.progress_percent.emit(0)
                    url = "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt.onnx"
                    self._download_file(url, model_path)

                class ComicTextDetectorONNX:
                    def __init__(self, path):
                        try:
                            import time
                            time.sleep(0.1)  # Yield GIL briefly so the UI can render before the heavy C++ initialization
                            import onnxruntime as ort
                            self.session = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
                            self.input_name = self.session.get_inputs()[0].name
                        except ImportError:
                            raise RuntimeError("The 'onnxruntime' module is not installed.\nPlease run 'pip install onnxruntime' in your terminal.")

                    def __call__(self, img_rgb):
                        import cv2
                        import numpy as np

                        h, w = img_rgb.shape[:2]

                        # 1. Letterbox resize to 1024x1024 (Model's expected input)
                        r = min(1024 / h, 1024 / w)
                        new_w, new_h = int(round(w * r)), int(round(h * r))
                        dw, dh = 1024 - new_w, 1024 - new_h

                        resized = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                        padded = cv2.copyMakeBorder(resized, 0, dh, 0, dw, cv2.BORDER_CONSTANT, value=(0, 0, 0))

                        # 2. Prepare tensor for ONNXRuntime
                        tensor = padded.astype(np.float32) / 255.0
                        tensor = np.transpose(tensor, (2, 0, 1))
                        tensor = np.expand_dims(tensor, 0)

                        # 3. Inference using ONNXRuntime (Multi-threaded & Highly Optimized)
                        outputs = self.session.run(None, {self.input_name: tensor})

                        # 4. Extract mask (Robustly finding the 1-channel dimension output map)
                        mask = None
                        for out in outputs:
                            if len(out.shape) == 4 and out.shape[1] == 1:
                                mask = out
                                break

                        if mask is None:
                            mask = outputs[1] if outputs[1].shape[1] == 1 else outputs[2]

                        mask = mask[0, 0]

                        # 5. Undo letterbox to original image size
                        mask = mask[:new_h, :new_w]
                        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)

                        return mask

                model = ComicTextDetectorONNX(model_path)
                self.process_finished.emit(model, self.model_name)

            elif self.model_name == "inpaint_model":
                import os
                model_path = "./models/lama_fp32.onnx"

                if not os.path.exists(model_path):
                    self.progress_percent.emit(0)
                    url = "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx"
                    self._download_file(url, model_path)

                class LamaONNXWrapper:
                    def __init__(self, path):
                        try:
                            import time
                            time.sleep(0.1)  # Yield GIL briefly so the UI can render before the heavy C++ initialization
                            import onnxruntime as ort
                            self.session = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
                        except ImportError:
                            raise RuntimeError("The 'onnxruntime' module is not installed.\nPlease run 'pip install onnxruntime' in your terminal.")

                    def __call__(self, img_512_rgb, mask_512):
                        import numpy as np

                        # Prepare image (1, 3, 512, 512) normalized to 0-1
                        img_tensor = img_512_rgb.astype(np.float32) / 255.0
                        img_tensor = np.transpose(img_tensor, (2, 0, 1))
                        img_tensor = np.expand_dims(img_tensor, 0)

                        # Prepare mask (1, 1, 512, 512) normalized to 0-1
                        mask_tensor = mask_512.astype(np.float32) / 255.0
                        mask_tensor = (mask_tensor > 0).astype(np.float32)
                        mask_tensor = np.expand_dims(mask_tensor, 0)
                        mask_tensor = np.expand_dims(mask_tensor, 0)

                        inputs = {
                            self.session.get_inputs()[0].name: img_tensor,
                            self.session.get_inputs()[1].name: mask_tensor
                        }

                        outputs = self.session.run(None, inputs)

                        res = outputs[0][0]
                        res = np.transpose(res, (1, 2, 0))
                        res = np.clip(res, 0, 255).astype(np.uint8)

                        return res

                model = LamaONNXWrapper(model_path)
                self.process_finished.emit(model, self.model_name)

        except Exception as e:
            self.error.emit(self.model_name, str(e))
