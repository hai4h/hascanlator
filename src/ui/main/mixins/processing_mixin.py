from PySide6.QtWidgets import QMessageBox
from src.core.detection_worker import DetectionWorker
from src.core.ocr_worker import BatchOCRWorker
from src.core.translation_worker import BatchTranslationWorker
from src.ui.canvas.items import BoundingBoxItem

class WorkerProcessingMixin:
    # --- DETECTION & OCR LOGIC ---
    def run_auto_detect(self):
        if not self.workspace.current_image_path or not self.yolo_model: return
        
        for item in self.scene.items():
            if isinstance(item, BoundingBoxItem) and getattr(item, 'is_auto', False):
                self.scene.removeItem(item)

        self.set_processing_lock(True)
        self.update_window_title("Detecting Text...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage("Detecting text regions...")
        
        self.detect_worker = DetectionWorker(self.workspace.current_image_path, self.yolo_model)
        self.detect_worker.finished.connect(self.on_detection_finished)
        self.detect_worker.error.connect(self.on_detection_error)
        self.detect_worker.start()

    def on_detection_finished(self, boxes):
        new_boxes = []
        for rect in boxes:
            box_item = BoundingBoxItem(rect, is_auto=True)
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
            self.ocr_worker.finished.connect(self.on_batch_ocr_finished)
            self.ocr_worker.start()
        else:
            self.progress_bar.setVisible(False)
            self.statusBar().showMessage("Detection Complete.")
            self.set_processing_lock(False)
            self.update_window_title()
            
        self.save_current_page_state()
        
    def on_detection_error(self, err_msg):
        QMessageBox.critical(self, "Detection Error", str(err_msg))
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Error during detection.")
        self.set_processing_lock(False)
        self.update_window_title()

    def run_ocr_on_selected(self):
        if not self.workspace.current_image_path or not self.current_selected_box or not self.mocr_model: return
        
        r = self.current_selected_box.sceneBoundingRect()
        crop_rect = (int(r.x()), int(r.y()), int(r.width()), int(r.height()))
        
        self.set_processing_lock(True)
        self.update_window_title("Reading text...")
        self.right_dock.ocr_input.setPlaceholderText("Reading text...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Reading selected box...")
        
        self.ocr_worker = BatchOCRWorker(self.mocr_model, self.workspace.current_image_path, [(crop_rect, self.current_selected_box)])
        self.ocr_worker.progress.connect(self.on_ocr_progress)
        self.ocr_worker.progress_percent.connect(self.progress_bar.setValue)
        self.ocr_worker.finished.connect(self.on_batch_ocr_finished)
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

    # --- TRANSLATION LOGIC ---
    def run_translation_on_selected(self):
        engine = self.settings.value("translation_engine", "google")
        if not self.workspace.current_image_path or not self.current_selected_box: 
            return
        if engine == "nmt" and not self.nmt_model:
            return
        
        self.set_processing_lock(True)
        self.update_window_title("Translating text...")
        self.right_dock.trans_input.setPlaceholderText("Translating...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Translating selected box...")
        
        boxes_data = [(self.current_selected_box.raw_text, self.current_selected_box)]
        self._start_translation_worker(engine, boxes_data)

    def run_translation_on_all(self):
        engine = self.settings.value("translation_engine", "google")
        if not self.workspace.current_image_path: 
            return
        if engine == "nmt" and not self.nmt_model:
            return
            
        boxes_data = []
        for item in self.scene.items():
            if isinstance(item, BoundingBoxItem) and item.raw_text.strip():
                boxes_data.append((item.raw_text, item))
                
        if not boxes_data:
            self.statusBar().showMessage("No OCR text found to translate.")
            return

        self.set_processing_lock(True)
        self.update_window_title("Translating all boxes...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Translating page...")
        
        self._start_translation_worker(engine, boxes_data)

    def _start_translation_worker(self, engine, boxes_data):
        src_lang = self.settings.value("trans_src", "ja")
        tgt_lang = self.settings.value("trans_tgt", "en")
        
        self.translation_worker = BatchTranslationWorker(engine, self.nmt_model, boxes_data, src_lang, tgt_lang)
        self.translation_worker.progress.connect(self.on_translation_progress)
        self.translation_worker.progress_percent.connect(self.progress_bar.setValue)
        self.translation_worker.finished.connect(self.on_batch_translation_finished)
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
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Translation Complete.")
        self.set_processing_lock(False)
        self.update_window_title()
        self.save_current_page_state()
        
    def on_translation_error(self, err_msg):
        QMessageBox.critical(self, "Translation Error", str(err_msg))
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("Error during translation.")
        self.set_processing_lock(False)
        self.update_window_title()