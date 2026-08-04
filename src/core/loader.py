from PySide6.QtCore import QThread, Signal
from abc import ABC, abstractmethod
import os

class ModelLoader(ABC):
    registry: dict[str, type] = {}

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        if hasattr(cls, 'model_key'):
            ModelLoader.registry[cls.model_key] = cls

    def __init__(self, nmt_repo_id="Helsinki-NLP/opus-mt-ja-en"):
        self.nmt_repo_id = nmt_repo_id

    @abstractmethod
    def load(self): ...

    def _hf_cache_dir(self):
        return os.path.abspath(os.path.join(os.getcwd(), "models", "hf_cache"))

class MangaOcrLoader(ModelLoader):
    model_key = "manga_ocr"
    def load(self):
        import torch
        from huggingface_hub import snapshot_download
        from manga_ocr import MangaOcr
        path = snapshot_download(repo_id="kha-white/manga-ocr-base", token=False, cache_dir=self._hf_cache_dir())
        mocr = MangaOcr(pretrained_model_name_or_path=path)

        # Ensure it uses GPU (CUDA/MPS) if available
        device_str = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        device = torch.device(device_str)
        if hasattr(mocr, 'device') and hasattr(mocr, 'model'):
            mocr.device = device
            mocr.model = mocr.model.to(device)

        return mocr

class YoloLoader(ModelLoader):
    model_key = "yolo_detector"
    def load(self):
        import torch
        from ultralytics import YOLO
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(repo_id="ogkalu/manga-text-detector-yolov8s", filename="manga-text-detector.pt", token=False, cache_dir=self._hf_cache_dir())
        model = YOLO(path)

        # Explicitly push YOLO to the best available hardware
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        model.to(device)

        return model

class NmtLoader(ModelLoader):
    model_key = "nmt_translator"
    def load(self):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from huggingface_hub import snapshot_download

        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        repo_id = self.nmt_repo_id
        path = snapshot_download(repo_id=repo_id, token=False, cache_dir=self._hf_cache_dir())

        tokenizer = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSeq2SeqLM.from_pretrained(path).to(device)

        class NMTWrapper:
            def __init__(self, tok, mod, repo, dev):
                self.tokenizer = tok
                self.model = mod
                self.repo = repo
                self.device = dev

            def __call__(self, text, src_lang="ja", tgt_lang="en"):
                if "nllb" in self.repo:
                    lang_map = {"auto": "jpn_Jpan", "ja": "jpn_Jpan", "en": "eng_Latn", "ko": "kor_Hang", "zh-CN": "zho_Hans", "vi": "vie_Latn", "es": "spa_Latn", "fr": "fra_Latn"}
                    self.tokenizer.src_lang = lang_map.get(src_lang, "jpn_Jpan")
                    inputs = self.tokenizer(text, return_tensors="pt", padding=True).to(self.device)
                    target_code = lang_map.get(tgt_lang, "eng_Latn")
                    forced_bos_token_id = self.tokenizer.lang_code_to_id.get(target_code, self.tokenizer.convert_tokens_to_ids(target_code))
                    translated_tokens = self.model.generate(**inputs, forced_bos_token_id=forced_bos_token_id)
                else:
                    inputs = self.tokenizer(text, return_tensors="pt", padding=True).to(self.device)
                    translated_tokens = self.model.generate(**inputs)
                res_text = self.tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
                return [{"translation_text": res_text}]

        return NMTWrapper(tokenizer, model, repo_id, device)

class MaskingLoader(ModelLoader):
    model_key = "masking_model"
    def load(self):
        model_path = "./models/comictextdetector.pt.onnx"
        if not os.path.exists(model_path):
            # Trigger download via worker progress signal fallback
            raise RuntimeError("Masking model not found. Please download via Settings.")

        class ComicTextDetectorONNX:
            def __init__(self, path):
                import time; time.sleep(0.1)
                import onnxruntime as ort

                # Fetch available providers and prioritize GPU / Hardware Accelerators over CPU
                available = ort.get_available_providers()
                preferred = ['CUDAExecutionProvider', 'MIGraphXExecutionProvider', 'ROCMExecutionProvider', 'DmlExecutionProvider', 'CoreMLExecutionProvider', 'CPUExecutionProvider']
                providers = [p for p in preferred if p in available]

                self.session = ort.InferenceSession(path, providers=providers)
                self.input_name = self.session.get_inputs()[0].name

            def __call__(self, img_rgb):
                import cv2, numpy as np
                h, w = img_rgb.shape[:2]
                r = min(1024 / h, 1024 / w)
                new_w, new_h = int(round(w * r)), int(round(h * r))
                dw, dh = 1024 - new_w, 1024 - new_h
                resized = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                padded = cv2.copyMakeBorder(resized, 0, dh, 0, dw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
                tensor = padded.astype(np.float32) / 255.0
                tensor = np.transpose(tensor, (2, 0, 1))
                tensor = np.expand_dims(tensor, 0)
                outputs = self.session.run(None, {self.input_name: tensor})
                mask = None
                for out in outputs:
                    if len(out.shape) == 4 and out.shape[1] == 1: mask = out; break
                if mask is None: mask = outputs[1] if outputs[1].shape[1] == 1 else outputs[2]
                mask = mask[0, 0]
                mask = mask[:new_h, :new_w]
                return cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)

        return ComicTextDetectorONNX(model_path)

class InpaintLoader(ModelLoader):
    model_key = "inpaint_model"
    def load(self):
        model_path = "./models/lama_fp32.onnx"
        if not os.path.exists(model_path):
            raise RuntimeError("LaMa model not found. Please download via Settings.")

        class LamaONNXWrapper:
            def __init__(self, path):
                import time; time.sleep(0.1)
                import onnxruntime as ort

                # Fetch available providers and prioritize GPU / Hardware Accelerators over CPU
                available = ort.get_available_providers()
                preferred = ['CUDAExecutionProvider', 'MIGraphXExecutionProvider', 'ROCMExecutionProvider', 'DmlExecutionProvider', 'CoreMLExecutionProvider', 'CPUExecutionProvider']
                providers = [p for p in preferred if p in available]

                self.session = ort.InferenceSession(path, providers=providers)

            def __call__(self, img_512_rgb, mask_512):
                import numpy as np
                img_tensor = img_512_rgb.astype(np.float32) / 255.0
                img_tensor = np.transpose(img_tensor, (2, 0, 1))
                img_tensor = np.expand_dims(img_tensor, 0)
                mask_tensor = mask_512.astype(np.float32) / 255.0
                mask_tensor = (mask_tensor > 0).astype(np.float32)
                mask_tensor = np.expand_dims(np.expand_dims(mask_tensor, 0), 0)
                inputs = {self.session.get_inputs()[0].name: img_tensor, self.session.get_inputs()[1].name: mask_tensor}
                outputs = self.session.run(None, inputs)
                res = outputs[0][0]
                res = np.transpose(res, (1, 2, 0))
                return np.clip(res, 0, 255).astype(np.uint8)

        return LamaONNXWrapper(model_path)

class ModelLoaderWorker(QThread):
    process_finished = Signal(object, str)
    error = Signal(str, str)
    progress_percent = Signal(int)

    def __init__(self, model_name, nmt_repo_id="Helsinki-NLP/opus-mt-ja-en"):
        super().__init__()
        self.model_name = model_name
        self.nmt_repo_id = nmt_repo_id
        self._download_file = self._download_file_impl # keep method available

    def _download_file_impl(self, url, dest):
        import urllib.request, os
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
                    if not chunk: break
                    out_file.write(chunk)
                    read_so_far += len(chunk)
                    self.progress_percent.emit(min(100, int((read_so_far * 100) / total_length)))
            else:
                out_file.write(response.read())

    def run(self):
        try:
            # Handle pre-download checks for local ONNX models
            if self.model_name == "masking_model" and not os.path.exists("./models/comictextdetector.pt.onnx"):
                self.progress_percent.emit(0)
                self._download_file("https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt.onnx", "./models/comictextdetector.pt.onnx")
            elif self.model_name == "inpaint_model" and not os.path.exists("./models/lama_fp32.onnx"):
                self.progress_percent.emit(0)
                self._download_file("https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx", "./models/lama_fp32.onnx")

            loader_cls = ModelLoader.registry.get(self.model_name)
            if not loader_cls:
                raise ValueError(f"Unknown model: {self.model_name}")

            loader = loader_cls(nmt_repo_id=self.nmt_repo_id)
            model = loader.load()
            self.process_finished.emit(model, self.model_name)

        except Exception as e:
            self.error.emit(self.model_name, str(e))
