import gc

from huggingface_hub import scan_cache_dir
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QProgressBar, QVBoxLayout

from src.core.loader import ModelLoaderWorker


class ModelProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Model Manager")

        self.setWindowFlags(
            Qt.Dialog
            | Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
            | Qt.WindowStaysOnTopHint
        )
        self.setWindowModality(Qt.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)

        self.lbl_status = QLabel("Preparing...")
        self.lbl_status.setTextFormat(Qt.RichText)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setMinimumWidth(450)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        layout.addWidget(self.lbl_status)
        layout.addSpacing(15)
        layout.addWidget(self.progress)

    def set_status(self, text):
        self.lbl_status.setText(text)

    def set_progress(self, val):
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(val)


class ModelManagementMixin:
    def is_model_downloaded(self, repo_id):
        """Checks if a model repository is already saved to the local cache."""
        import os

        if repo_id == "local_masking":
            return os.path.exists("./models/comictextdetector.pt.onnx")
        if repo_id == "local_inpaint":
            return os.path.exists("./models/lama_fp32.onnx")
        if repo_id == "local":
            return True

        cache = getattr(self, "_download_cache", None)
        if cache is None:
            self._download_cache = {}
            cache = self._download_cache
        if repo_id in cache:
            return cache[repo_id]

        try:
            cache_dir = os.path.abspath(os.path.join(os.getcwd(), "models", "hf_cache"))
            if not os.path.exists(cache_dir):
                cache[repo_id] = False
                return False

            hf_cache_info = scan_cache_dir(cache_dir)
            for repo in hf_cache_info.repos:
                if repo.repo_id == repo_id:
                    cache[repo_id] = True
                    return True
            cache[repo_id] = False
            return False
        except Exception:
            return False

    def _invalidate_model_cache(self):
        """Forces is_model_downloaded to re-scan the disk (after load/delete events)."""
        if hasattr(self, "_download_cache"):
            self._download_cache.clear()

    def ensure_models_ready(self, required_models):
        """Checks a list of (model_key, repo_id) tuples. Prompts once for all missing models."""
        missing = []
        loading = []

        for model_key, repo_id in required_models:
            is_loaded = False
            if (
                model_key == "manga_ocr"
                and self.mocr_model is not None
                or model_key == "yolo_detector"
                and self.yolo_model is not None
                or model_key == "nmt_translator"
                and self.nmt_model is not None
                or model_key == "masking_model"
                and self.masking_model is not None
                or model_key == "inpaint_model"
                and self.inpaint_model is not None
            ):
                is_loaded = True

            if is_loaded:
                continue

            is_loading = False
            if (
                (model_key == "manga_ocr" and self.mocr_is_loading)
                or (model_key == "yolo_detector" and self.yolo_is_loading)
                or (model_key == "nmt_translator" and self.nmt_is_loading)
                or (model_key == "masking_model" and self.masking_is_loading)
                or (model_key == "inpaint_model" and self.inpaint_is_loading)
                or (model_key in self.model_load_queue)
            ):
                is_loading = True

            if is_loading:
                loading.append(model_key)
            else:
                missing.append((model_key, repo_id))

        if not missing and not loading:
            return True

        if missing:
            model_names = {
                "manga_ocr": "MangaOCR (Text Recognition)",
                "yolo_detector": "YOLOv8 Bubble Detector",
                "nmt_translator": "Local Offline NMT Engine",
                "masking_model": "Text Masking Model (comictextdetector)",
                "inpaint_model": "Image Inpainting Model (LaMa)",
            }

            names_str = "\n".join([f"- {model_names.get(k, k)}" for k, r in missing])

            reply = QMessageBox.question(
                self,
                "Models Not Loaded",
                f"The following required models are not loaded:\n{names_str}\n\nWould you like to load them now?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                not_downloaded = [
                    k for k, r in missing if not self.is_model_downloaded(r)
                ]
                downloaded = [k for k, r in missing if self.is_model_downloaded(r)]

                for k in downloaded:
                    self.load_model(k)

                if not_downloaded:
                    st_reply = QMessageBox.question(
                        self,
                        "Models Not Downloaded",
                        "Some models are not downloaded yet.\nWould you like to go to Settings to download them?",
                        QMessageBox.Yes | QMessageBox.No,
                    )
                    if st_reply == QMessageBox.Yes:
                        tab_idx = (
                            1
                            if len(not_downloaded) == 1
                            and not_downloaded[0] == "nmt_translator"
                            else 0
                        )
                        self.open_settings(tab_index=tab_idx)
                elif downloaded:
                    QMessageBox.information(
                        self,
                        "Loading Started",
                        "Started loading models into RAM.\nPlease try your action again once they finish.",
                    )
        elif loading:
            QMessageBox.information(
                self, "Loading", "Required models are currently loading. Please wait."
            )

        return False

    # --- MODEL LOADING LOGIC ---
    def load_model(self, model_name):
        if model_name not in self.model_load_queue:
            self.model_load_queue.append(model_name)
            self.model_status_changed.emit()
        self._process_model_queue()

    def _process_model_queue(self):
        if self.is_loading_model_seq or not self.model_load_queue:
            return

        model_name = self.model_load_queue.pop(0)
        self.is_loading_model_seq = True

        if (
            not hasattr(self, "model_progress_dialog")
            or self.model_progress_dialog is None
        ):
            self.model_progress_dialog = ModelProgressDialog(self)

        readable_names = {
            "manga_ocr": "MangaOCR (Text Recognition)",
            "yolo_detector": "YOLOv8 Bubble Detector",
            "nmt_translator": "Local Offline NMT Engine",
            "masking_model": "Text Masking Model (comictextdetector)",
            "inpaint_model": "Image Inpainting Model (LaMa)",
        }
        r_name = readable_names.get(model_name, model_name)

        self.model_progress_dialog.set_status(
            f"Downloading / Loading:<br><b>{r_name}</b>...<br><br>(This might take a while for the first time downloading)"
        )
        self.model_progress_dialog.progress.setRange(0, 0)
        self.model_progress_dialog.show()
        self.model_progress_dialog.raise_()
        self.model_progress_dialog.activateWindow()

        if model_name == "manga_ocr":
            self.mocr_is_loading = True
        elif model_name == "yolo_detector":
            self.yolo_is_loading = True
        elif model_name == "nmt_translator":
            self.nmt_is_loading = True
        elif model_name == "masking_model":
            self.masking_is_loading = True
        elif model_name == "inpaint_model":
            self.inpaint_is_loading = True

        self.update_window_title()
        self.model_status_changed.emit()
        self.update_button_states()

        nmt_repo_id = self.settings.value(
            "nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en"
        )
        loader = ModelLoaderWorker(model_name, nmt_repo_id=nmt_repo_id)

        self.loader_threads.append(loader)
        if hasattr(loader, "progress_percent"):
            loader.progress_percent.connect(self.model_progress_dialog.set_progress)

        loader.process_finished.connect(
            lambda m, n, t=loader: self.on_model_loaded(m, n, t)
        )
        loader.error.connect(lambda n, e, t=loader: self.on_model_error(n, e, t))
        loader.start()

    def on_model_loaded(self, model, name, thread_ref):
        if name == "manga_ocr":
            self.mocr_model, self.mocr_is_loading = model, False
        elif name == "yolo_detector":
            self.yolo_model, self.yolo_is_loading = model, False
        elif name == "nmt_translator":
            self.nmt_model, self.nmt_is_loading = model, False
        elif name == "masking_model":
            self.masking_model, self.masking_is_loading = model, False
        elif name == "inpaint_model":
            if self.inpaint_model is not None and self.inpaint_model is not model:
                try:
                    self.inpaint_model.close()
                except Exception:
                    pass
            self.inpaint_model, self.inpaint_is_loading = model, False

        if thread_ref in self.loader_threads:
            self.loader_threads.remove(thread_ref)
        try:
            thread_ref.process_finished.disconnect()
            thread_ref.error.disconnect()
            if hasattr(thread_ref, "progress_percent"):
                thread_ref.progress_percent.disconnect()
        except RuntimeError:
            pass  # already disconnected
        thread_ref.wait(2000)
        thread_ref.deleteLater()

        self.is_loading_model_seq = False

        self._invalidate_model_cache()

        if (
            not self.model_load_queue
            and hasattr(self, "model_progress_dialog")
            and self.model_progress_dialog
        ):
            self.model_progress_dialog.hide()

        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit()
        self._process_model_queue()

    def on_model_error(self, name, err, thread_ref):
        if (
            not self.model_load_queue
            and hasattr(self, "model_progress_dialog")
            and self.model_progress_dialog
        ):
            self.model_progress_dialog.hide()

        QMessageBox.critical(self, "Model Load Error", f"Failed to load {name}:\n{err}")

        if name == "manga_ocr":
            self.mocr_is_loading = False
        elif name == "yolo_detector":
            self.yolo_is_loading = False
        elif name == "nmt_translator":
            self.nmt_is_loading = False
        elif name == "masking_model":
            self.masking_is_loading = False
        elif name == "inpaint_model":
            self.inpaint_is_loading = False

        if thread_ref in self.loader_threads:
            self.loader_threads.remove(thread_ref)
        try:
            thread_ref.process_finished.disconnect()
            thread_ref.error.disconnect()
            if hasattr(thread_ref, "progress_percent"):
                thread_ref.progress_percent.disconnect()
        except RuntimeError:
            pass
        thread_ref.wait(2000)
        thread_ref.deleteLater()

        self.is_loading_model_seq = False
        self._invalidate_model_cache()
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit()
        self._process_model_queue()

    def unload_model(self, model_name):
        if model_name == "manga_ocr":
            self.mocr_model = None
        elif model_name == "yolo_detector":
            self.yolo_model = None
        elif model_name == "nmt_translator":
            self.nmt_model = None
        elif model_name == "masking_model":
            self.masking_model = None
        elif model_name == "inpaint_model":
            if self.inpaint_model is not None:
                try:
                    self.inpaint_model.close()
                except Exception:
                    pass
            self.inpaint_model = None

        gc.collect()
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit()
