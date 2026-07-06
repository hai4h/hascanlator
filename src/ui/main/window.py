import os
import gc
import psutil
import cv2
import numpy as np

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGraphicsScene, QGraphicsPixmapItem, QFileDialog, QMessageBox, QProgressBar, QLabel
)
from PySide6.QtCore import Qt, QRectF, Signal, QSettings, QTimer
from PySide6.QtGui import QPixmap, QImage

from src.core.workspace import WorkspaceManager
from src.core.detection_worker import DetectionWorker
from src.core.loader_worker import ModelLoaderWorker
from src.core.ocr_worker import BatchOCRWorker
from src.core.translation_worker import BatchTranslationWorker

from src.ui.canvas.view import MangaCanvasView
from src.ui.canvas.items import BoundingBoxItem

from src.ui.settings.dialog import SettingsDialog

from src.ui.main.panels import EditorDockWidget
from src.ui.main.toolbar import MainToolbar
from src.ui.main.navigation import BottomNavigation

class HAScanlatorWindow(QMainWindow):
    model_status_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HAScanlator")
        self.resize(1300, 800)
        
        self.settings = QSettings("HAScanlatorTeam", "HAScanlator")
        self.workspace = WorkspaceManager()
        
        self.current_image_item = None
        self.current_selected_box = None
        self._updating_ui = False 
        self.is_processing = False 
        
        self.mocr_model, self.mocr_is_loading = None, False
        self.yolo_model, self.yolo_is_loading = None, False
        self.nmt_model, self.nmt_is_loading = None, False

        self.model_load_queue = []
        self.is_loading_model_seq = False
        
        self.loader_threads = [] 
        self.ocr_worker = None
        self.detect_worker = None
        self.translation_worker = None

        self._setup_ui()
        self._connect_signals()
        
        self.update_window_title()
        self.update_button_states()

        if self.settings.value("auto_load_mocr", False, type=bool):
            self.load_model("manga_ocr")
        if self.settings.value("auto_load_yolo", False, type=bool):
            self.load_model("yolo_detector")
        if self.settings.value("auto_load_nmt", False, type=bool):
            self.load_model("nmt_translator")

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.toolbar = MainToolbar(self)
        self.nav = BottomNavigation(self)
        self.right_dock = EditorDockWidget(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
        
        center_area = QWidget()
        center_layout = QVBoxLayout(center_area)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scene = QGraphicsScene()
        self.view = MangaCanvasView(self.scene)
        
        center_layout.addWidget(self.view, stretch=1)
        center_layout.addWidget(self.nav)
        
        main_layout.addWidget(self.toolbar)
        main_layout.addWidget(center_area, stretch=1) 

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        
        self.ram_lbl = QLabel("RAM: 0.00 GB")
        self.ram_lbl.setStyleSheet("padding-left: 10px; padding-right: 10px; color: #888;")
        self.statusBar().addPermanentWidget(self.ram_lbl)
        
        try:
            self.system_total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            self.system_total_ram_gb = 0.0
        
        self.ram_timer = QTimer(self)
        self.ram_timer.timeout.connect(self._update_ram_usage)
        self.ram_timer.start(2000) 
        self._update_ram_usage()
        
        self.statusBar().showMessage("Ready")

    def _connect_signals(self):
        self.toolbar.btn_load.clicked.connect(self.load_images_dialog)
        self.toolbar.btn_reset.clicked.connect(self.reset_workspace)
        
        # Image Manipulation Signals
        self.toolbar.btn_peek.pressed.connect(self.show_original_image)
        self.toolbar.btn_peek.released.connect(self.show_edited_image)
        self.toolbar.btn_undo.clicked.connect(self.undo_edit)
        
        self.toolbar.btn_auto_detect.clicked.connect(self.run_auto_detect)
        self.toolbar.btn_add_box.clicked.connect(self.add_test_box)
        self.toolbar.btn_settings.clicked.connect(lambda: SettingsDialog(self).exec())
        
        self.toolbar.chk_auto_process.setChecked(self.settings.value("auto_process", False, type=bool))
        self.toolbar.chk_auto_process.stateChanged.connect(
            lambda: self.settings.setValue("auto_process", self.toolbar.chk_auto_process.isChecked())
        )

        self.nav.btn_prev.clicked.connect(self.prev_image)
        self.nav.btn_next.clicked.connect(self.next_image)

        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.right_dock.btn_run_ocr.clicked.connect(self.run_ocr_on_selected)
        self.right_dock.btn_delete_box.clicked.connect(self.delete_selected_box)
        self.right_dock.ocr_input.textChanged.connect(self.on_ocr_text_edited)
        self.right_dock.trans_input.textChanged.connect(self.on_trans_text_edited)
        self.right_dock.btn_translate_box.clicked.connect(self.run_translation_on_selected)
        self.right_dock.btn_translate_all.clicked.connect(self.run_translation_on_all)
        
        # Typesetting Signals
        self.right_dock.btn_clean_bubble.clicked.connect(self.smart_clean_bubble)
        self.right_dock.btn_toggle_typeset.clicked.connect(self.toggle_typeset_view)
        
        self.right_dock.btn_align_left.clicked.connect(lambda: self.set_text_alignment(Qt.AlignLeft))
        self.right_dock.btn_align_center.clicked.connect(lambda: self.set_text_alignment(Qt.AlignCenter))
        self.right_dock.btn_align_right.clicked.connect(lambda: self.set_text_alignment(Qt.AlignRight))
        
        self.right_dock.btn_indent_plus.clicked.connect(lambda: self.set_text_indent(5))
        self.right_dock.btn_indent_minus.clicked.connect(lambda: self.set_text_indent(-5))

    def closeEvent(self, event):
        if self.scene:
            self.scene.selectionChanged.disconnect(self.on_selection_changed)
        event.accept()

    def update_window_title(self, custom_status=None):
        title = "HAScanlator"
        if self.mocr_is_loading or self.yolo_is_loading:
            title += " - Loading Models..."
        elif custom_status:
            title += f" - {custom_status}"
        
        if self.workspace.has_images:
            title += f"   |   [{self.workspace.current_page_number}/{self.workspace.total_pages}] {self.workspace.current_filename}"
            
        self.setWindowTitle(title)

    def update_button_states(self):
        has_image = self.workspace.has_images
        has_box = self.current_selected_box is not None
        
        # Toolbar State
        self.toolbar.btn_peek.setEnabled(has_image)
        if has_image and len(self.workspace.undo_stacks.get(self.workspace.current_image_path, [])) > 0:
            self.toolbar.btn_undo.setEnabled(True)
        else:
            self.toolbar.btn_undo.setEnabled(False)
        
        if self.yolo_model is None:
            self.toolbar.btn_auto_detect.setEnabled(False)
            self.toolbar.btn_auto_detect.setText("Auto Detect\n(Detector Required)")
        else:
            self.toolbar.btn_auto_detect.setEnabled(not self.is_processing and has_image)
            self.toolbar.btn_auto_detect.setText("Auto Detect\n(Whole Page)")
            
        # OCR / Trans State
        if self.mocr_model is None:
            self.right_dock.btn_run_ocr.setEnabled(False)
            self.right_dock.btn_run_ocr.setText("OCR Model Required")
        else:
            self.right_dock.btn_run_ocr.setEnabled(not self.is_processing and has_image and has_box)
            self.right_dock.btn_run_ocr.setText("Run OCR on Box")

        if self.nmt_model is None:
            self.right_dock.btn_translate_box.setEnabled(False)
            self.right_dock.btn_translate_box.setText("Translator Required")
            self.right_dock.btn_translate_all.setEnabled(False)
        else:
            self.right_dock.btn_translate_box.setEnabled(not self.is_processing and has_image and has_box)
            self.right_dock.btn_translate_box.setText("Translate Box")
            self.right_dock.btn_translate_all.setEnabled(not self.is_processing and has_image)
            
        # Typesetting State
        self.right_dock.btn_clean_bubble.setEnabled(not self.is_processing and has_image and has_box)
        self.right_dock.btn_toggle_typeset.setEnabled(has_box)
        self.right_dock.btn_align_left.setEnabled(has_box)
        self.right_dock.btn_align_center.setEnabled(has_box)
        self.right_dock.btn_align_right.setEnabled(has_box)
        self.right_dock.btn_indent_minus.setEnabled(has_box)
        self.right_dock.btn_indent_plus.setEnabled(has_box)
            
        # Navigation
        self.nav.btn_prev.setEnabled(not self.is_processing and self.workspace.current_img_index > 0)
        self.nav.btn_next.setEnabled(not self.is_processing and self.workspace.current_img_index < self.workspace.total_pages - 1)

    def _update_ram_usage(self):
        try:
            process = psutil.Process(os.getpid())
            app_gb_usage = process.memory_info().rss / (1024 ** 3)
            
            if getattr(self, 'system_total_ram_gb', 0.0) > 0:
                self.ram_lbl.setText(f"RAM: {app_gb_usage:.2f} GB / {self.system_total_ram_gb:.1f} GB")
            else:
                self.ram_lbl.setText(f"RAM: {app_gb_usage:.2f} GB")
        except Exception:
            pass

    def set_processing_lock(self, locked):
        self.is_processing = locked
        self.update_button_states()

    # --- OPENCV IMAGE HELPERS ---
    def imread_utf8(self, filepath):
        """Allows cv2 to load files that contain non-ascii characters in their folder path."""
        img_array = np.fromfile(filepath, np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    def cv2_to_qpixmap(self, cv_img):
        """Converts an OpenCV BGR numpy array to QPixmap for rendering."""
        h, w, ch = cv_img.shape
        bytes_per_line = ch * w
        converted = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        qimg = QImage(converted.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)

    # --- PEEK AND UNDO LOGIC ---
    def show_original_image(self):
        path = self.workspace.current_image_path
        if path and path in self.workspace.original_images:
            self.current_image_item.setPixmap(self.cv2_to_qpixmap(self.workspace.original_images[path]))

    def show_edited_image(self):
        path = self.workspace.current_image_path
        if path and path in self.workspace.edited_images:
            self.current_image_item.setPixmap(self.cv2_to_qpixmap(self.workspace.edited_images[path]))

    def undo_edit(self):
        path = self.workspace.current_image_path
        if path and self.workspace.undo_stacks.get(path):
            last_img = self.workspace.undo_stacks[path].pop()
            self.workspace.edited_images[path] = last_img
            self.show_edited_image()
            self.update_button_states()

    def smart_clean_bubble(self):
        if not self.workspace.current_image_path or not self.current_selected_box: return
        path = self.workspace.current_image_path
        
        # 1. Save Undo State
        current_img = self.workspace.edited_images[path].copy()
        self.workspace.undo_stacks[path].append(current_img)
        if len(self.workspace.undo_stacks[path]) > 5:
            self.workspace.undo_stacks[path].pop(0)
            
        rect = self.current_selected_box.sceneBoundingRect()
        x, y, w, h = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        
        img = self.workspace.edited_images[path]
        
        # 2. Boundary Safety Check
        x, y = max(0, x), max(0, y)
        w, h = min(img.shape[1] - x, w), min(img.shape[0] - y, h)
        if w <= 0 or h <= 0: return
        
        roi = img[y:y+h, x:x+w]
        
        # 3. Smart Masking
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # Use Otsu's thresholding to find the core black text
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        clean_mask = np.zeros_like(gray)
        
        for contour in contours:
            cx, cy, cw, ch = cv2.boundingRect(contour)
            
            # Filter 1: Edge touching (increased margin slightly to 3 for safety)
            margin = 3
            touches_edge = (cx <= margin) or (cy <= margin) or (cx + cw >= w - margin) or (cy + ch >= h - margin)
            
            # Filter 2: Too huge
            area = cv2.contourArea(contour)
            too_huge = area > (w * h * 0.5)
            
            if not touches_edge and not too_huge:
                cv2.drawContours(clean_mask, [contour], -1, 255, thickness=cv2.FILLED)
        
        # 4. Aggressive Mask Expansion
        # Use an Ellipse kernel to evenly expand the mask in all directions
        # Iterations=2 makes the mask fat enough to completely swallow grey JPEG artifacts
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        clean_mask = cv2.dilate(clean_mask, kernel, iterations=2)
        
        # 5. Erase text
        # Radius 7 forces the algorithm to look further away (past the halo) for clean replacement colors
        cleaned_roi = cv2.inpaint(roi, clean_mask, 7, cv2.INPAINT_TELEA)
        
        img[y:y+h, x:x+w] = cleaned_roi
        
        # 6. Save and Render
        self.workspace.edited_images[path] = img
        self.show_edited_image()
        self.update_button_states()

    # --- TYPESETTING CONTROLS ---
    def toggle_typeset_view(self):
        if not self.current_selected_box: return
        self.current_selected_box.toggle_typeset()
        
    def set_text_alignment(self, align):
        if not self.current_selected_box: return
        self.current_selected_box.align = align
        if self.current_selected_box.is_typeset:
            self.current_selected_box.update_typeset()

    def set_text_indent(self, delta):
        if not self.current_selected_box: return
        self.current_selected_box.indent = max(0, self.current_selected_box.indent + delta)
        if self.current_selected_box.is_typeset:
            self.current_selected_box.update_typeset()

    # --- MODEL LOADING LOGIC ---
    def load_model(self, model_name):
        if model_name not in self.model_load_queue:
            self.model_load_queue.append(model_name)
            self.model_status_changed.emit()
        self._process_model_queue()

    def _process_model_queue(self):
        if self.is_loading_model_seq or not self.model_load_queue: return
            
        model_name = self.model_load_queue.pop(0)
        self.is_loading_model_seq = True

        if model_name == "manga_ocr": self.mocr_is_loading = True
        elif model_name == "yolo_detector": self.yolo_is_loading = True
        elif model_name == "nmt_translator": self.nmt_is_loading = True
            
        self.update_window_title()
        self.model_status_changed.emit()
        self.update_button_states()
        
        loader = ModelLoaderWorker(model_name)
        self.loader_threads.append(loader)
        loader.finished.connect(lambda m, n, t=loader: self.on_model_loaded(m, n, t))
        loader.error.connect(lambda n, e, t=loader: self.on_model_error(n, e, t))
        loader.start()

    def on_model_loaded(self, model, name, thread_ref):
        if name == "manga_ocr":
            self.mocr_model, self.mocr_is_loading = model, False
        elif name == "yolo_detector":
            self.yolo_model, self.yolo_is_loading = model, False
        elif name == "nmt_translator":
            self.nmt_model, self.nmt_is_loading = model, False

        if thread_ref in self.loader_threads: self.loader_threads.remove(thread_ref)
            
        self.is_loading_model_seq = False
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit() 
        self._process_model_queue() 

    def on_model_error(self, name, err, thread_ref):
        QMessageBox.critical(self, "Model Load Error", f"Failed to load {name}:\n{err}")
        if name == "manga_ocr": self.mocr_is_loading = False
        elif name == "yolo_detector": self.yolo_is_loading = False
        elif name == "nmt_translator": self.nmt_is_loading = False
            
        if thread_ref in self.loader_threads: self.loader_threads.remove(thread_ref)
            
        self.is_loading_model_seq = False
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit()
        self._process_model_queue() 

    def unload_model(self, model_name):
        if model_name == "manga_ocr": self.mocr_model = None
        elif model_name == "yolo_detector": self.yolo_model = None
        elif model_name == "nmt_translator": self.nmt_model = None
            
        gc.collect() 
        self.update_window_title()
        self.update_button_states()
        self.model_status_changed.emit()

    # --- WORKSPACE & NAVIGATION LOGIC ---
    def load_images_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Manga Pages", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_paths:
            self.workspace.load_images(file_paths)
            self.render_current_page()

    def reset_workspace(self):
        self.workspace.reset()
        self.current_image_item = None
        self.scene.clear()
        self.nav.update_labels(0, 0)
        self.update_window_title()
        self.update_button_states()
        self.statusBar().showMessage("Workspace Reset")

    def render_current_page(self):
        if not self.workspace.has_images: return

        path = self.workspace.current_image_path
        self.nav.update_labels(self.workspace.current_page_number, self.workspace.total_pages)
        
        self.scene.clear() 
        
        # --- Memory Injection for Image Processing ---
        if path not in self.workspace.original_images:
            cv_img = self.imread_utf8(path)
            self.workspace.original_images[path] = cv_img.copy()
            self.workspace.edited_images[path] = cv_img.copy()
            self.workspace.undo_stacks[path] = []

        pixmap = self.cv2_to_qpixmap(self.workspace.edited_images[path])
        self.current_image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.current_image_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

        # Restore cached boxes
        cached_data = self.workspace.get_page_state(path)
        if cached_data:
            for b_data in cached_data:
                box = BoundingBoxItem(b_data['rect'], is_auto=b_data['is_auto'])
                box.setPos(b_data['pos'])
                box.raw_text, box.translated_text = b_data['raw_text'], b_data['translated_text']
                box.align = b_data.get('align', Qt.AlignCenter)
                box.indent = b_data.get('indent', 5)
                self.scene.addItem(box)
                
                # Apply visual Typesetting state if it was toggled on
                if b_data.get('is_typeset', False):
                    box.toggle_typeset(force_state=True)
                
        self.update_window_title()
        self.update_button_states()
        
        if not self.workspace.is_page_processed(path) and self.toolbar.chk_auto_process.isChecked() and self.yolo_model:
            QTimer.singleShot(100, self.run_auto_detect)

    def save_current_page_state(self):
        if not self.workspace.current_image_path: return
        boxes = [{
            'rect': item.rect(), 'pos': item.scenePos(), 'is_auto': item.is_auto,
            'raw_text': item.raw_text, 'translated_text': item.translated_text,
            'is_typeset': getattr(item, 'is_typeset', False),
            'align': getattr(item, 'align', Qt.AlignCenter),
            'indent': getattr(item, 'indent', 5)
        } for item in self.scene.items() if isinstance(item, BoundingBoxItem)]
        self.workspace.save_page_state(self.workspace.current_image_path, boxes)

    def prev_image(self):
        if not self.is_processing:
            self.save_current_page_state()
            if self.workspace.prev_page(): self.render_current_page()

    def next_image(self):
        if not self.is_processing:
            self.save_current_page_state()
            if self.workspace.next_page(): self.render_current_page()

    # --- ITEM INTERACTION LOGIC ---
    def on_selection_changed(self):
        boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        dock = self.right_dock
        
        if len(boxes) == 1:
            self.current_selected_box = boxes[0]
            self._updating_ui = True 
            dock.ocr_input.setEnabled(True)
            dock.trans_input.setEnabled(True)
            dock.btn_delete_box.setEnabled(True)
            dock.ocr_input.setPlainText(self.current_selected_box.raw_text)
            dock.trans_input.setPlainText(self.current_selected_box.translated_text)
            self._updating_ui = False 
        else:
            self.current_selected_box = None
            self._updating_ui = True
            dock.ocr_input.clear()
            dock.trans_input.clear()
            dock.ocr_input.setEnabled(False)
            dock.trans_input.setEnabled(False)
            dock.btn_delete_box.setEnabled(False)
            self._updating_ui = False
            
        self.update_button_states()

    def on_ocr_text_edited(self):
        if not self._updating_ui and self.current_selected_box:
            self.current_selected_box.raw_text = self.right_dock.ocr_input.toPlainText()

    def on_trans_text_edited(self):
        if not self._updating_ui and self.current_selected_box:
            self.current_selected_box.translated_text = self.right_dock.trans_input.toPlainText()
            if self.current_selected_box.is_typeset:
                self.current_selected_box.update_typeset()

    def add_test_box(self):
        if not self.current_image_item: return
        center = self.view.mapToScene(self.view.viewport().rect().center())
        box = BoundingBoxItem(QRectF(center.x() - 50, center.y() - 100, 100, 200), is_auto=False)
        self.scene.addItem(box)
        self.scene.clearSelection()
        box.setSelected(True)

    def delete_selected_box(self):
        if self.current_selected_box:
            self.scene.removeItem(self.current_selected_box)

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