from PySide6.QtWidgets import QMessageBox
from src.core.detection import DetectionWorker
from src.core.ocr import BatchOCRWorker
from src.core.translation import BatchTranslationWorker
from src.ui.canvas.items import BoundingBoxItem

class WorkerProcessingMixin:
    # --- DETECTION & OCR LOGIC ---
    def _get_translation_requirements(self, boxes):
        reqs = []
        engine = self.settings.value("translation_engine", "google")
        if engine == "nmt":
            repo_id = self.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en")
            reqs.append(("nmt_translator", repo_id))

        if any(not getattr(b, 'raw_text', '').strip() for b in boxes):
            reqs.append(("manga_ocr", "kha-white/manga-ocr-base"))

        return reqs

    def _check_and_run_ocr_first(self, boxes, next_action):
        """Checks if any boxes are missing OCR text. If so, runs OCR first and chains to the next action."""
        boxes_needing_ocr = [b for b in boxes if not getattr(b, 'raw_text', '').strip()]
        if boxes_needing_ocr:
            if not self.mocr_model:
                return True # Fallback failsafe, should be handled by ensure_models_ready upstream

            self._pending_post_ocr_action = next_action
            self.set_processing_lock(True)
            self.update_window_title("Reading missing text...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.statusBar().showMessage(f"Running OCR on {len(boxes_needing_ocr)} boxes...")

            boxes_data = []
            for box in boxes_needing_ocr:
                r = box.sceneBoundingRect()
                boxes_data.append(((int(r.x()), int(r.y()), int(r.width()), int(r.height())), box))

            self.ocr_worker = BatchOCRWorker(self.mocr_model, self.workspace.current_image_path, boxes_data)
            self.ocr_worker.progress.connect(self.on_ocr_progress)
            self.ocr_worker.progress_percent.connect(self.progress_bar.setValue)
            self.ocr_worker.process_finished.connect(self.on_batch_ocr_finished)
            self.ocr_worker.error.connect(self.on_ocr_error)
            self.ocr_worker.start()
            return True
        return False

    def run_auto_detect(self):
        if not self.workspace.current_image_path: return

        reqs = [
            ("yolo_detector", "ogkalu/manga-text-detector-yolov8s"),
            ("manga_ocr", "kha-white/manga-ocr-base")
        ]
        if not self.ensure_models_ready(reqs): return

        self._pending_history_msg = "Auto Detect (YOLO + OCR)"

        for item in self.scene.items():
            if isinstance(item, BoundingBoxItem) and getattr(item, 'is_auto', False):
                self.scene.removeItem(item)

        self.set_processing_lock(True)
        self.update_window_title("Detecting Text...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage("Detecting text regions...")

        self.detect_worker = DetectionWorker(self.workspace.current_image_path, self.yolo_model)
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

        if self.mocr_model and new_boxes:
            self.update_window_title("Reading Text...")
            self.statusBar().showMessage("Performing Optical Character Recognition...")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

            boxes_data = [( (int(b.sceneBoundingRect().x()), int(b.sceneBoundingRect().y()),
                             int(b.sceneBoundingRect().width()), int(b.sceneBoundingRect().height())), b)
                          for b in new_boxes]

            self.ocr_worker = BatchOCRWorker(self.mocr_model, self.workspace.current_image_path, boxes_data)
            self.ocr_worker.progress.connect(self.on_ocr_progress)
            self.ocr_worker.progress_percent.connect(self.progress_bar.setValue)
            self.ocr_worker.process_finished.connect(self.on_batch_ocr_finished)
            self.ocr_worker.error.connect(self.on_ocr_error)
            self.ocr_worker.start()
        else:
            self.progress_bar.setVisible(False)
            self.statusBar().showMessage("Detection Complete.")
            self.set_processing_lock(False)
            self.update_window_title()
            msg = getattr(self, '_pending_history_msg', "Auto Detect")
            self.commit_history(msg)

        self.save_current_page_state()


    def on_detection_error(self, err_msg):
        QMessageBox.critical(self, "Detection Error", str(err_msg))
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Error during detection.")
        self.set_processing_lock(False)
        self.update_window_title()

    def run_ocr_on_selected(self):
        selected_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        if not self.workspace.current_image_path or not selected_boxes: return
        if not self.ensure_models_ready([("manga_ocr", "kha-white/manga-ocr-base")]): return

        self._pending_history_msg = f"Run OCR ({len(selected_boxes)} Selected)"
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

        self.ocr_worker = BatchOCRWorker(self.mocr_model, self.workspace.current_image_path, boxes_data)
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
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Processing Complete.")
        self.set_processing_lock(False)
        self.update_window_title()

        msg = getattr(self, '_pending_history_msg', "Batch OCR")
        self.commit_history(msg)

        # Resume chained workflow if another action triggered OCR on-the-fly
        if hasattr(self, '_pending_post_ocr_action') and self._pending_post_ocr_action:
            action = self._pending_post_ocr_action
            self._pending_post_ocr_action = None
            action()

    def on_ocr_error(self, err_msg):
        QMessageBox.critical(self, "OCR Error", str(err_msg))
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Error during OCR.")
        self.set_processing_lock(False)
        self.update_window_title()

        if hasattr(self, '_pending_post_ocr_action'):
            self._pending_post_ocr_action = None

    # --- TRANSLATION LOGIC ---
    def run_translation_on_selected(self):
        selected_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        if not self.workspace.current_image_path or not selected_boxes: return

        reqs = self._get_translation_requirements(selected_boxes)
        if reqs and not self.ensure_models_ready(reqs): return

        if self._check_and_run_ocr_first(selected_boxes, self.run_translation_on_selected):
            return

        engine = self.settings.value("translation_engine", "google")
        if engine == "nmt":
            repo_id = self.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en")
            if not self.ensure_model_ready("nmt_translator", repo_id): return

        boxes_data = [(box.raw_text, box) for box in selected_boxes if box.raw_text.strip()]
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
        self._auto_clean_and_typeset = False
        self._start_translation_worker(engine, boxes_data)

    def run_translate_typeset_selected(self):
        selected_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        if not self.workspace.current_image_path or not selected_boxes:
            return

        reqs = self._get_translation_requirements(selected_boxes)
        if reqs and not self.ensure_models_ready(reqs): return

        if self._check_and_run_ocr_first(selected_boxes, self.run_translate_typeset_selected):
            return

        engine = self.settings.value("translation_engine", "google")
        if engine == "nmt":
            repo_id = self.settings.value("nmt_model_repo", "Helsinki-NLP/opus-mt-ja-en")
            if not self.ensure_model_ready("nmt_translator", repo_id): return

        boxes_data = [(box.raw_text, box) for box in selected_boxes if box.raw_text.strip()]
        if not boxes_data:
            self.statusBar().showMessage("No valid OCR text found in selection to translate.")
            return

        self.set_processing_lock(True)
        self.update_window_title("Translating & Typesetting...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"Processing {len(boxes_data)} selected boxes...")

        self._pending_history_msg = f"Translate & Typeset ({len(boxes_data)} Selected)"
        self._auto_clean_and_typeset = True
        self._auto_typeset_boxes = [box for _, box in boxes_data]
        self._start_translation_worker(engine, boxes_data)

    def run_translate_typeset_all(self):
        if not self.workspace.current_image_path:
            return

        all_boxes = [item for item in self.scene.items() if isinstance(item, BoundingBoxItem)]
        if not all_boxes:
            self.statusBar().showMessage("No boxes found on page.")
            return

        reqs = self._get_translation_requirements(all_boxes)
        if reqs and not self.ensure_models_ready(reqs): return

        if self._check_and_run_ocr_first(all_boxes, self.run_translate_typeset_all):
            return

        engine = self.settings.value("translation_engine", "google")

        boxes_data = [(item.raw_text, item) for item in all_boxes if item.raw_text.strip()]

        if not boxes_data:
            self.statusBar().showMessage("No valid OCR text found on page to translate.")
            return

        self.set_processing_lock(True)
        self.update_window_title("Translating & Typesetting All...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"Processing {len(boxes_data)} boxes on page...")

        self._pending_history_msg = f"Translate & Typeset All ({len(boxes_data)} Boxes)"
        self._auto_clean_and_typeset = True
        self._auto_typeset_boxes = [box for _, box in boxes_data]
        self._start_translation_worker(engine, boxes_data)

    def _start_translation_worker(self, engine, boxes_data):
        src_lang = self.settings.value("trans_src", "ja")
        tgt_lang = self.settings.value("trans_tgt", "en")

        self.translation_worker = BatchTranslationWorker(engine, self.nmt_model, boxes_data, src_lang, tgt_lang)
        self.translation_worker.progress.connect(self.on_translation_progress)
        self.translation_worker.progress_percent.connect(self.progress_bar.setValue)
        self.translation_worker.process_finished.connect(self.on_batch_translation_finished)
        self.translation_worker.error.connect(self.on_translation_error)
        self.translation_worker.start()

    def on_translation_progress(self, translated_text, box_item_ref):
        box_item_ref.translated_text = translated_text
        if self.current_selected_box == box_item_ref:
            self._updating_ui = True
            self.right_dock.trans_input.setPlainText(translated_text)
            self._updating_ui = False

            if self.current_selected_box.is_typeset:
                self.current_selected_box.update_typeset()

    def on_batch_translation_finished(self):
        if getattr(self, '_auto_clean_and_typeset', False):
            if hasattr(self, '_auto_typeset_boxes') and self._auto_typeset_boxes:
                self.smart_clean_bubble(boxes=self._auto_typeset_boxes)
                for box in self._auto_typeset_boxes:
                    box.toggle_typeset(force_state=True)

            self._auto_clean_and_typeset = False
            self._auto_typeset_boxes = []

        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Translation Complete.")
        self.set_processing_lock(False)
        self.update_window_title()
        self.save_current_page_state()

        msg = getattr(self, '_pending_history_msg', "Batch Translate & Typeset")
        self.commit_history(msg)

    def on_translation_error(self, err_msg):
        QMessageBox.critical(self, "Translation Error", str(err_msg))
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Error during translation.")
        self.set_processing_lock(False)
        self.update_window_title()
