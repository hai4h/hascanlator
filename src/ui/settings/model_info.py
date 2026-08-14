import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QThread, Signal


def _format_size(num_bytes):
    if num_bytes is None:
        return "Unknown"
    mb = num_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.1f} MB"


class ModelInfoWorker(QThread):
    """Collects model info (sizes, available providers) off the UI thread."""
    finished_ok = Signal(dict)

    def __init__(self, meta, parent=None):
        super().__init__(parent)
        self.meta = meta

    def run(self):
        info = {}
        try:
            local_path = self.meta.get("local_path")
            if local_path and os.path.exists(local_path):
                info["size_on_disk"] = os.path.getsize(local_path)

            repo_id = self.meta.get("repo")
            if repo_id and not repo_id.startswith("local_"):
                cache_dir = os.path.abspath(os.path.join(os.getcwd(), "models", "hf_cache"))
                try:
                    from huggingface_hub import scan_cache_dir
                    hf_cache_info = scan_cache_dir(cache_dir)
                    for repo in hf_cache_info.repos:
                        if repo.repo_id == repo_id:
                            info["cache_size"] = repo.size_on_disk
                            break
                except Exception:
                    pass

                try:
                    from huggingface_hub import HfApi
                    model_info = HfApi().model_info(repo_id, files_metadata=True)
                    total = sum(s.size for s in model_info.siblings if s.size is not None)
                    info["remote_size"] = total if total > 0 else None
                except Exception:
                    info["remote_size"] = None

            if self.meta.get("kind") == "onnx":
                try:
                    import onnxruntime as ort
                    info["providers_available"] = ort.get_available_providers()
                except Exception:
                    info["providers_available"] = ["CPUExecutionProvider"]
            else:
                available = ["CPU"]
                try:
                    import torch
                    if torch.cuda.is_available():
                        available.append("CUDA")
                    elif torch.version.cuda:
                        available.append(f"CUDA (build {torch.version.cuda}, no GPU detected)")
                    mps = getattr(torch.backends, "mps", None)
                    if mps is not None and mps.is_available():
                        available.append("MPS")
                except Exception:
                    pass
                info["providers_available"] = available
        except Exception:
            pass
        self.finished_ok.emit(info)


class ModelInfoDialog(QDialog):
    """Shows size, source and inference provider info for a single model."""

    def __init__(self, main_window, meta):
        super().__init__(main_window)
        self.main_window = main_window
        self.meta = meta
        self._worker = None
        self.setWindowTitle(f"Model Info - {meta['title']}")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Model:", QLabel(f"<b>{meta['title']}</b>"))

        source = meta.get("source", "")
        if "{repo}" in source:
            source = source.format(repo=meta.get("repo", ""))
        if meta.get("local_path"):
            source = f"{source}<br><span style='color:grey'>{meta['local_path']}</span>"
        self.lbl_source = QLabel(source)
        self.lbl_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_source.setWordWrap(True)
        form.addRow("Source:", self.lbl_source)

        self.lbl_size = QLabel("Collecting...")
        form.addRow("Size on disk:", self.lbl_size)

        self.lbl_remote = QLabel("Collecting...")
        form.addRow("Remote size:", self.lbl_remote)

        self.lbl_inuse = QLabel()
        form.addRow("In use:", self.lbl_inuse)

        self.lbl_available = QLabel("Checking...")
        self.lbl_available.setWordWrap(True)
        form.addRow("Available:", self.lbl_available)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._set_live_provider()
        self._worker = ModelInfoWorker(meta)
        self._worker.finished_ok.connect(self._on_info)
        self._worker.start()

    def _set_live_provider(self):
        mw = self.main_window
        key = self.meta["key"]
        model = getattr(mw, {
            "manga_ocr": "mocr_model",
            "yolo_detector": "yolo_model",
            "masking_model": "masking_model",
            "inpaint_model": "inpaint_model",
            "nmt_translator": "nmt_model",
        }.get(key, ""), None)
        if model is not None:
            prov = getattr(model, "providers", None)
            dev = getattr(model, "device", None)
            if prov:
                self.lbl_inuse.setText(", ".join(prov))
            elif dev is not None:
                self.lbl_inuse.setText(str(dev))
            else:
                self.lbl_inuse.setText("Loaded (provider unknown)")
        else:
            self.lbl_inuse.setText("Not loaded")

    def _on_info(self, info):
        local_size = info.get("size_on_disk") or info.get("cache_size")
        if local_size:
            self.lbl_size.setText(_format_size(local_size))
        else:
            self.lbl_size.setText("Not downloaded")

        if self.meta.get("kind") == "onnx" and info.get("size_on_disk"):
            self.lbl_remote.setText(_format_size(info["size_on_disk"]))
        elif info.get("remote_size") is not None:
            self.lbl_remote.setText(_format_size(info["remote_size"]))
        else:
            self.lbl_remote.setText("Unknown (offline)")

        if info.get("providers_available"):
            self.lbl_available.setText(", ".join(info["providers_available"]))

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.finished_ok.disconnect()
            except RuntimeError:
                pass
            self.main_window._orphaned_workers.append(self._worker)
        super().closeEvent(event)