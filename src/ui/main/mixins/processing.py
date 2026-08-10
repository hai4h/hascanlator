from PySide6.QtWidgets import QMessageBox

from src.core.detection import DetectionWorker
from src.core.ocr import BatchOCRWorker
from src.core.translation import BatchTranslationWorker
from src.ui.canvas.items import BoundingBoxItem


class WorkerProcessingMixin:
    def __init__(self):
        self._active_workers = []

    def _register_worker(self, worker):
        """Prevents QThread memory leaks by tracking and auto-cleaning workers."""
        self._active_workers.append(worker)
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        return worker

    def _cleanup_worker(self, worker):
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        worker.deleteLater()

    def _cleanup_pipeline(self):
        self._is_auto_scan_pipeline = False
        self._active_pipeline_boxes = []
        self._pipeline_flags = {}
        self.progress_bar.setVisible(False)
        self.set_processing_lock(False)
        self.update_window_title()

    def _get_translation_requirements(self, boxes):
        reqs = []
        engine = self.settings.value("translation_engine", "google")
        if engine == "nmt":
            repo_id = self.settings.value(
                "nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en"
            )
            reqs.append(("nmt_translator", repo_id))

        if any(not getattr(b, "raw_text", "").strip() for b in boxes):
            reqs.append(("manga_ocr", "kha-white/manga-ocr-base"))

        return reqs

    def _check_and_run_ocr_first(self, boxes, next_action):
        """Checks if any boxes are missing OCR text. If so, runs OCR first and chains to the next action."""
        boxes_needing_ocr = [b for b in boxes if not getattr(b, "raw_text", "").strip()]
        if boxes_needing_ocr:
            if not self.mocr_model:
                return False  # Fallback failsafe, should be handled by ensure_models_ready upstream

            self._pending_post_ocr_action = next_action
            self.set_processing_lock(True)
            self.update_window_title("Reading missing text...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.statusBar().showMessage(
                f"Running OCR on {len(boxes_needing_ocr)} boxes..."
            )

            boxes_data = []
            for box in boxes_needing_ocr:
                r = box.sceneBoundingRect()
                boxes_data.append(
                    ((int(r.x()), int(r.y()), int(r.width()), int(r.height())), box)
                )

            self.ocr_worker = self._register_worker(
                BatchOCRWorker(
                    self.mocr_model, self.workspace.current_image_path, boxes_data
                )
            )
            self.ocr_worker.progress.connect(self.on_ocr_progress)
            self.ocr_worker.progress_percent.connect(self.progress_bar.setValue)
            self.ocr_worker.process_finished.connect(self.on_batch_ocr_finished)
            self.ocr_worker.error.connect(self.on_ocr_error)
            self.ocr_worker.start()
            return True
        return False

    def _execute_pipeline_clean_typeset(self):
        """Final execution arm in the auto-process sequence."""
        boxes = getattr(self, "_active_pipeline_boxes", [])
        flags = getattr(self, "_pipeline_flags", {})

        if flags.get("inpaint") and boxes:
            # Chains mask -> inpaint -> typeset
            self.inpaint_bubble_mask(boxes=boxes, commit=False)
            return
        elif flags.get("mask") and boxes:
            # Chains mask -> typeset
            self.generate_bubble_mask(boxes=boxes, auto_inpaint=False, commit=False)
            return

        self._execute_pipeline_post_inpaint()

    def _execute_pipeline_post_inpaint(self):
        boxes = getattr(self, "_active_pipeline_boxes", [])
        flags = getattr(self, "_pipeline_flags", {})

        if flags.get("typeset") and boxes:
            for box in boxes:
                box.toggle_typeset(force_state=True)

        self.statusBar().showMessage("Processing Complete.")

        msg = getattr(self, "_pending_history_msg", "Auto Process")
        self.commit_history(msg)
        self.save_current_page_state()

        self._cleanup_pipeline()

    def run_auto_detect(self):
        if not self.workspace.current_image_path:
            return

        do_ocr = self.settings.value("auto_scan_ocr", True, type=bool)
        do_trans = self.settings.value("auto_scan_translate", False, type=bool)
        do_mask = self.settings.value("auto_scan_mask", False, type=bool)
        do_inpaint = self.settings.value("auto_scan_inpaint", False, type=bool)
        do_type = self.settings.value("auto_scan_typeset", False, type=bool)

        reqs = [("yolo_detector", "ogkalu/manga-text-detector-yolov8s")]
        if do_ocr or do_trans or do_type:
            reqs.append(("manga_ocr", "kha-white/manga-ocr-base"))
            do_ocr = True  # Enforce OCR if trans or typeset is requested

        if do_trans or do_type:
            engine = self.settings.value("translation_engine", "google")
            if engine == "nmt":
                reqs.append(
                    (
                        "nmt_translator",
                        self.settings.value(
                            "nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en"
                        ),
                    )
                )
            do_trans = True

        if do_inpaint:
            do_mask = True

        if do_mask:
            reqs.append(("masking_model", "local_masking"))
        if do_inpaint:
            reqs.append(("inpaint_model", "local_inpaint"))

        if not self.ensure_models_ready(reqs):
            return

        # Dynamically build the log message
        tasks = ["YOLO"]
        if do_ocr:
            tasks.append("OCR")
        if do_trans:
            tasks.append("Translate")
        if do_mask:
            tasks.append("Mask")
        if do_inpaint:
            tasks.append("Inpaint")
        if do_type:
            tasks.append("Typeset")

        self._pending_history_msg = f"Auto Pipeline ({', '.join(tasks)})"

        self._is_auto_scan_pipeline = True
        self._pipeline_flags = {
            "ocr": do_ocr,
            "trans": do_trans,
            "mask": do_mask,
            "inpaint": do_inpaint,
            "typeset": do_type,
        }
        self._active_pipeline_boxes = []

        for item in self.scene.items():
            if isinstance(item, BoundingBoxItem) and getattr(item, "is_auto", False):
                self.scene.removeItem(item)

        self.set_processing_lock(True)
        self.update_window_title("Detecting Text...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage("Detecting text regions...")

        self.detect_worker = self._register_worker(
            DetectionWorker(self.workspace.current_image_path, self.yolo_model)
        )
        self.detect_worker.process_finished.connect(self.on_detection_finished)
        self.detect_worker.error.connect(self.on_detection_error)
        self.detect_worker.start()

    def on_detection_finished(self, boxes):
        new_boxes = []
        for rect in boxes:
            box_item = BoundingBoxItem(rect, is_auto=True)
            self.apply_default_font_settings(box_item)
            self.scene.addItem(box_item)
            new_boxes.append(box_item)

        flags = getattr(self, "_pipeline_flags", {})
        self._active_pipeline_boxes = new_boxes

        if getattr(self, "_is_auto_scan_pipeline", False):
            if flags.get("ocr") and new_boxes:
                self.update_window_title("Reading Text...")
                self.statusBar().showMessage(
                    "Performing Optical Character Recognition..."
                )
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(0)

                boxes_data = [
                    (
                        (
                            int(b.sceneBoundingRect().x()),
                            int(b.sceneBoundingRect().y()),
                            int(b.sceneBoundingRect().width()),
                            int(b.sceneBoundingRect().height()),
                        ),
                        b,
                    )
                    for b in new_boxes
                ]

                self.ocr_worker = self._register_worker(
                    BatchOCRWorker(
                        self.mocr_model, self.workspace.current_image_path, boxes_data
                    )
                )
                self.ocr_worker.progress.connect(self.on_ocr_progress)
                self.ocr_worker.progress_percent.connect(self.progress_bar.setValue)
                self.ocr_worker.process_finished.connect(self.on_batch_ocr_finished)
                self.ocr_worker.error.connect(self.on_ocr_error)
                self.ocr_worker.start()
                return
            else:
                self._execute_pipeline_clean_typeset()
                return

        # Normal finish (Fallback)
        msg = getattr(self, "_pending_history_msg", "Auto Detect")
        self.commit_history(msg)
        self.save_current_page_state()
        self._cleanup_pipeline()

    def on_detection_error(self, err_msg):
        QMessageBox.critical(self, "Detection Error", str(err_msg))
        self.statusBar().showMessage("Error during detection.")
        self._cleanup_pipeline()

    def run_ocr_on_selected(self):
        selected_boxes = [
            item
            for item in self.scene.selectedItems()
            if isinstance(item, BoundingBoxItem)
        ]
        if not self.workspace.current_image_path or not selected_boxes:
            return
        if not self.ensure_models_ready([("manga_ocr", "kha-white/manga-ocr-base")]):
            return

        self._pending_history_msg = f"Run OCR ({len(selected_boxes)} Selected)"
        self._is_auto_scan_pipeline = True
        self._pipeline_flags = {
            "trans": False,
            "mask": False,
            "inpaint": False,
            "typeset": False,
        }
        self._active_pipeline_boxes = selected_boxes
        self.set_processing_lock(True)
        self.update_window_title("Reading text...")
        self.right_dock.ocr_input.setPlaceholderText("Reading text...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"Reading {len(selected_boxes)} selected boxes...")

        boxes_data = []
        for box in selected_boxes:
            r = box.sceneBoundingRect()
            crop_rect = (int(r.x()), int(r.y()), int(r.width()), int(r.height()))
            boxes_data.append((crop_rect, box))

        self.ocr_worker = self._register_worker(
            BatchOCRWorker(
                self.mocr_model, self.workspace.current_image_path, boxes_data
            )
        )
        self.ocr_worker.progress.connect(self.on_ocr_progress)
        self.ocr_worker.progress_percent.connect(self.progress_bar.setValue)
        self.ocr_worker.process_finished.connect(self.on_batch_ocr_finished)
        self.ocr_worker.error.connect(self.on_ocr_error)
        self.ocr_worker.start()

    def on_ocr_progress(self, text, box_item_ref):
        box_item_ref.raw_text = text
        if self.current_selected_box == box_item_ref:
            self._updating_ui = True
            self.right_dock.ocr_input.setPlainText(text)
            self._updating_ui = False

    def on_batch_ocr_finished(self):
        # Resume chained workflow if another action triggered OCR on-the-fly
        if hasattr(self, "_pending_post_ocr_action") and self._pending_post_ocr_action:
            action = self._pending_post_ocr_action
            self._pending_post_ocr_action = None
            action()
            return

        flags = getattr(self, "_pipeline_flags", {})
        boxes = getattr(self, "_active_pipeline_boxes", [])

        if getattr(self, "_is_auto_scan_pipeline", False):
            if flags.get("trans") and boxes:
                boxes_data = [
                    (box.raw_text, box) for box in boxes if box.raw_text.strip()
                ]
                if boxes_data:
                    engine = self.settings.value("translation_engine", "google")
                    self._start_translation_worker(engine, boxes_data)
                    return

            self._execute_pipeline_clean_typeset()
            return

        # Normal finish (Fallback)
        msg = getattr(self, "_pending_history_msg", "Batch OCR")
        self.commit_history(msg)
        self._cleanup_pipeline()

    def on_ocr_error(self, err_msg):
        QMessageBox.critical(self, "OCR Error", str(err_msg))
        self.statusBar().showMessage("Error during OCR.")

        if hasattr(self, "_pending_post_ocr_action"):
            self._pending_post_ocr_action = None

        self._cleanup_pipeline()

    # --- TRANSLATION LOGIC ---
    def run_translation_on_selected(self):
        selected_boxes = [
            item
            for item in self.scene.selectedItems()
            if isinstance(item, BoundingBoxItem)
        ]
        if not self.workspace.current_image_path or not selected_boxes:
            return

        reqs = self._get_translation_requirements(selected_boxes)
        if reqs and not self.ensure_models_ready(reqs):
            return

        if self._check_and_run_ocr_first(
            selected_boxes, self.run_translation_on_selected
        ):
            return

        engine = self.settings.value("translation_engine", "google")

        boxes_data = [
            (box.raw_text, box) for box in selected_boxes if box.raw_text.strip()
        ]
        if not boxes_data:
            self.statusBar().showMessage("No OCR text found in selection.")
            return

        self.set_processing_lock(True)
        self.update_window_title("Translating text...")
        self.right_dock.trans_input.setPlaceholderText("Translating...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"Translating {len(boxes_data)} selected boxes...")

        self._pending_history_msg = f"Translate ({len(boxes_data)} Selected)"
        self._is_auto_scan_pipeline = True
        self._pipeline_flags = {
            "mask": False,
            "inpaint": False,
            "typeset": False,
            "trans": True,
        }
        self._active_pipeline_boxes = selected_boxes
        self._start_translation_worker(engine, boxes_data)

    def run_translate_typeset_selected(self):
        selected_boxes = [
            item
            for item in self.scene.selectedItems()
            if isinstance(item, BoundingBoxItem)
        ]
        if not self.workspace.current_image_path or not selected_boxes:
            return

        reqs = self._get_translation_requirements(selected_boxes)
        reqs.append(("masking_model", "local_masking"))
        reqs.append(("inpaint_model", "local_inpaint"))
        if reqs and not self.ensure_models_ready(reqs):
            return

        if self._check_and_run_ocr_first(
            selected_boxes, self.run_translate_typeset_selected
        ):
            return

        engine = self.settings.value("translation_engine", "google")

        boxes_data = [
            (box.raw_text, box) for box in selected_boxes if box.raw_text.strip()
        ]
        if not boxes_data:
            self.statusBar().showMessage(
                "No valid OCR text found in selection to translate."
            )
            return

        self.set_processing_lock(True)
        self.update_window_title("Translating & Typesetting...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"Processing {len(boxes_data)} selected boxes...")

        self._pending_history_msg = f"Translate & Typeset ({len(boxes_data)} Selected)"
        self._is_auto_scan_pipeline = True
        self._pipeline_flags = {
            "mask": True,
            "inpaint": True,
            "typeset": True,
            "trans": True,
        }
        self._active_pipeline_boxes = selected_boxes
        self._start_translation_worker(engine, boxes_data)

    def _start_translation_worker(self, engine, boxes_data):
        src_lang = self.settings.value("trans_src", "ja")
        tgt_lang = self.settings.value("trans_tgt", "en")

        self.translation_worker = self._register_worker(
            BatchTranslationWorker(
                engine, self.nmt_model, boxes_data, src_lang, tgt_lang
            )
        )
        self.translation_worker.progress.connect(self.on_translation_progress)
        self.translation_worker.progress_percent.connect(self.progress_bar.setValue)
        self.translation_worker.process_finished.connect(
            self.on_batch_translation_finished
        )
        self.translation_worker.error.connect(self.on_translation_error)
        self.translation_worker.start()

    def on_translation_progress(self, translated_text, box_item_ref):
        import re

        # 1. Convert scattered full-width Japanese dots into standard ellipses
        if self.settings.value("format_ellipsis_standard", True, type=bool):
            # Matches any sequence of 2 or more dots/ellipses, ignoring spaces or line-breaks between them
            translated_text = re.sub(
                r"[\.．。・…‥](?:\s*[\.．。・…‥])+", "...", translated_text
            )

        # 2. Break ellipses onto their own line to prevent awkward wide bounding box stretch
        if self.settings.value("format_ellipsis_newline", True, type=bool):
            # Safely pad any sequence of 2+ dots or real ellipses with newlines
            translated_text = re.sub(r"(\.{2,}|…+)", r"\n\1\n", translated_text)
            # Reconstruct the string to automatically collapse empty lines and trim trailing/leading spaces
            translated_text = "\n".join(
                [line.strip() for line in translated_text.splitlines() if line.strip()]
            )

        box_item_ref.translated_text = translated_text
        if self.current_selected_box == box_item_ref:
            self._updating_ui = True
            self.right_dock.trans_input.setPlainText(translated_text)
            self._updating_ui = False

            if self.current_selected_box.is_typeset:
                self.current_selected_box.update_typeset()

    def on_batch_translation_finished(self):
        if getattr(self, "_is_auto_scan_pipeline", False):
            self._execute_pipeline_clean_typeset()
            return

        # Normal finish (Fallback)
        self.save_current_page_state()
        msg = getattr(self, "_pending_history_msg", "Batch Translate & Typeset")
        self.commit_history(msg)
        self._cleanup_pipeline()

    def on_translation_error(self, err_msg):
        QMessageBox.critical(self, "Translation Error", str(err_msg))
        self.statusBar().showMessage("Error during translation.")
        self._cleanup_pipeline()
