import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QGraphicsScene, QGraphicsPixmapItem, 
    QDockWidget, QTextEdit, QLabel, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QRectF, Signal, QSettings
from PySide6.QtGui import QPixmap

from src.ui.canvas import MangaCanvasView, BoundingBoxItem
from src.ui.settings import SettingsDialog
from src.core.workers import ModelLoaderWorker, BatchOCRWorker, DetectionWorker

class HAScanlatorWindow(QMainWindow):
    model_status_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HAScanlator")
        self.resize(1300, 800)
        
        self.settings = QSettings("HAScanlatorTeam", "HAScanlator")

        self.image_paths = []
        self.current_img_index = -1
        self.page_data_cache = {} 
        self.current_image_path = None
        
        self.current_image_item = None
        self.current_selected_box = None
        self._updating_ui = False 
        
        self.mocr_model = None
        self.mocr_is_loading = False
        
        self.yolo_model = None
        self.yolo_is_loading = False
        
        self.is_processing = False 
        
        self.loader_threads = [] 
        self.ocr_worker = None
        self.detect_worker = None

        self._setup_ui()
        self.update_window_title()

        if self.settings.value("auto_load_mocr", False, type=bool):
            self.load_model("manga_ocr")
        if self.settings.value("auto_load_yolo", False, type=bool):
            self.load_model("yolo_detector")

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedWidth(130)
        toolbar_layout = QVBoxLayout(toolbar)
        
        btn_load = QPushButton("Load Images")
        btn_load.clicked.connect(self.load_images_dialog)
        
        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("<")
        self.btn_prev.clicked.connect(self.prev_image)
        self.btn_next = QPushButton(">")
        self.btn_next.clicked.connect(self.next_image)
        self.lbl_page = QLabel("0 / 0")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)

        self.btn_auto_detect = QPushButton("Auto Detect\n(Whole Page)")
        self.btn_auto_detect.clicked.connect(self.run_auto_detect)
        self.btn_auto_detect.setEnabled(False)
        
        btn_add_box = QPushButton("Add Box (Manual)")
        btn_add_box.clicked.connect(self.add_test_box)

        btn_settings = QPushButton("Settings")
        btn_settings.clicked.connect(self.open_settings)
        
        toolbar_layout.addWidget(btn_load)
        toolbar_layout.addLayout(nav_layout)
        toolbar_layout.addWidget(self.lbl_page)
        toolbar_layout.addWidget(QLabel("")) 
        toolbar_layout.addWidget(self.btn_auto_detect)
        toolbar_layout.addWidget(btn_add_box)
        toolbar_layout.addStretch() 
        toolbar_layout.addWidget(btn_settings)
        
        # Canvas
        self.scene = QGraphicsScene()
        self.view = MangaCanvasView(self.scene)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        
        main_layout.addWidget(toolbar)
        main_layout.addWidget(self.view, stretch=1) 

        # Right Panel
        self.right_dock = QDockWidget("Editor & Workflow", self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)
        self._setup_right_panel()

    def _setup_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.ocr_input = QTextEdit()
        self.ocr_input.setStyleSheet("font-size: 16px;")
        self.trans_input = QTextEdit()
        
        tools_layout = QHBoxLayout()
        self.btn_run_ocr = QPushButton("Run OCR on Box")
        self.btn_run_ocr.clicked.connect(self.run_ocr_on_selected)
        
        self.btn_delete_box = QPushButton("Delete Box")
        self.btn_delete_box.clicked.connect(self.delete_selected_box)
        
        tools_layout.addWidget(self.btn_run_ocr)
        tools_layout.addWidget(self.btn_delete_box)

        self.btn_run_ocr.setEnabled(False)
        self.btn_delete_box.setEnabled(False)
        self.ocr_input.setEnabled(False)
        self.trans_input.setEnabled(False)
        
        self.ocr_input.textChanged.connect(self.on_ocr_text_edited)
        self.trans_input.textChanged.connect(self.on_trans_text_edited)
        
        layout.addLayout(tools_layout)
        layout.addWidget(QLabel("Raw Text (OCR):"))
        layout.addWidget(self.ocr_input)
        layout.addWidget(QLabel("Translation:"))
        layout.addWidget(self.trans_input)
        self.right_dock.setWidget(panel)

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
        
        if self.image_paths and self.current_img_index >= 0:
            filename = os.path.basename(self.current_image_path)
            title += f"   |   [{self.current_img_index + 1}/{len(self.image_paths)}] {filename}"
            
        self.setWindowTitle(title)

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def load_model(self, model_name):
        if model_name == "manga_ocr": self.mocr_is_loading = True
        elif model_name == "yolo_detector": self.yolo_is_loading = True
            
        self.update_window_title()
        self.model_status_changed.emit()
        
        loader_thread = ModelLoaderWorker(model_name)
        self.loader_threads.append(loader_thread)
        
        loader_thread.finished.connect(lambda m, n, t=loader_thread: self.on_model_loaded(m, n, t))
        loader_thread.error.connect(lambda n, e, t=loader_thread: self.on_model_error(n, e, t))
        loader_thread.start()

    def on_model_loaded(self, model, name, thread_ref):
        if name == "manga_ocr":
            self.mocr_model = model
            self.mocr_is_loading = False
            self.settings.setValue("auto_load_mocr", True) 
        elif name == "yolo_detector":
            self.yolo_model = model
            self.yolo_is_loading = False
            self.settings.setValue("auto_load_yolo", True)

        if thread_ref in self.loader_threads:
            self.loader_threads.remove(thread_ref)
            
        self.on_selection_changed()
        self.update_window_title()
        self.model_status_changed.emit() 

    def on_model_error(self, name, err, thread_ref):
        QMessageBox.critical(self, "Model Load Error", f"Failed to load {name}:\n{err}")
        if name == "manga_ocr": self.mocr_is_loading = False
        elif name == "yolo_detector": self.yolo_is_loading = False
            
        if thread_ref in self.loader_threads:
            self.loader_threads.remove(thread_ref)
            
        self.update_window_title()
        self.model_status_changed.emit()

    def on_selection_changed(self):
        boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        if len(boxes) == 1:
            self.current_selected_box = boxes[0]
            self._updating_ui = True 
            self.ocr_input.setEnabled(True)
            self.trans_input.setEnabled(True)
            self.btn_delete_box.setEnabled(True)
            self.ocr_input.setPlainText(self.current_selected_box.raw_text)
            self.trans_input.setPlainText(self.current_selected_box.translated_text)
            
            self.btn_run_ocr.setEnabled(self.mocr_model is not None)
            if self.mocr_model is None:
                self.btn_run_ocr.setText("MangaOCR Not Loaded")
            else:
                self.btn_run_ocr.setText("Run OCR on Box")
                
            self._updating_ui = False 
        else:
            self.current_selected_box = None
            self._updating_ui = True
            self.ocr_input.clear()
            self.trans_input.clear()
            self.ocr_input.setEnabled(False)
            self.trans_input.setEnabled(False)
            self.btn_run_ocr.setEnabled(False)
            self.btn_delete_box.setEnabled(False)
            self.btn_run_ocr.setText("Run OCR on Box")
            self._updating_ui = False

    def on_ocr_text_edited(self):
        if not self._updating_ui and self.current_selected_box:
            self.current_selected_box.raw_text = self.ocr_input.toPlainText()

    def on_trans_text_edited(self):
        if not self._updating_ui and self.current_selected_box:
            self.current_selected_box.translated_text = self.trans_input.toPlainText()

    def load_images_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Manga Pages", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_paths:
            self.image_paths = sorted(file_paths) 
            self.current_img_index = 0
            self.page_data_cache.clear() 
            self.render_current_page()

    def render_current_page(self):
        if self.current_img_index < 0 or self.current_img_index >= len(self.image_paths):
            return

        self.current_image_path = self.image_paths[self.current_img_index]
        self.lbl_page.setText(f"{self.current_img_index + 1} / {len(self.image_paths)}")
        self.btn_prev.setEnabled(self.current_img_index > 0)
        self.btn_next.setEnabled(self.current_img_index < len(self.image_paths) - 1)
        self.btn_auto_detect.setEnabled(True)
        self.update_window_title()
        
        self.scene.clear() 
        
        pixmap = QPixmap(self.current_image_path)
        self.current_image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.current_image_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

        if self.current_image_path in self.page_data_cache:
            for b_data in self.page_data_cache[self.current_image_path]:
                box = BoundingBoxItem(b_data['rect'], is_auto=b_data['is_auto'])
                box.setPos(b_data['pos'])
                box.raw_text = b_data['raw_text']
                box.translated_text = b_data['translated_text']
                self.scene.addItem(box)

    def save_current_page_state(self):
        if not self.current_image_path: return
        boxes = []
        for item in self.scene.items():
            if isinstance(item, BoundingBoxItem):
                boxes.append({
                    'rect': item.rect(),
                    'pos': item.scenePos(),
                    'is_auto': item.is_auto,
                    'raw_text': item.raw_text,
                    'translated_text': item.translated_text
                })
        self.page_data_cache[self.current_image_path] = boxes

    def prev_image(self):
        if self.current_img_index > 0 and not self.is_processing:
            self.save_current_page_state()
            self.current_img_index -= 1
            self.render_current_page()

    def next_image(self):
        if self.current_img_index < len(self.image_paths) - 1 and not self.is_processing:
            self.save_current_page_state()
            self.current_img_index += 1
            self.render_current_page()

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

    def set_processing_lock(self, locked):
        self.is_processing = locked
        self.btn_prev.setEnabled(not locked and self.current_img_index > 0)
        self.btn_next.setEnabled(not locked and self.current_img_index < len(self.image_paths) - 1)
        self.btn_auto_detect.setEnabled(not locked)
        self.btn_run_ocr.setEnabled(not locked and self.mocr_model is not None and self.current_selected_box is not None)

    def run_auto_detect(self):
        if not self.current_image_path: return
        
        items = self.scene.items()
        for item in items:
            if isinstance(item, BoundingBoxItem) and getattr(item, 'is_auto', False):
                self.scene.removeItem(item)

        self.set_processing_lock(True)
        self.update_window_title("Finding Text Bubbles...")
        
        self.detect_worker = DetectionWorker(self.current_image_path, self.yolo_model)
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
            self.update_window_title("Auto-Reading Text...")
            boxes_data = []
            for box in new_boxes:
                r = box.sceneBoundingRect()
                crop_rect = (int(r.x()), int(r.y()), int(r.width()), int(r.height()))
                boxes_data.append((crop_rect, box))
                
            self.ocr_worker = BatchOCRWorker(self.mocr_model, self.current_image_path, boxes_data)
            self.ocr_worker.progress.connect(self.on_ocr_progress)
            self.ocr_worker.finished.connect(self.on_batch_ocr_finished)
            self.ocr_worker.start()
        else:
            self.set_processing_lock(False)
            self.update_window_title()
        
    def on_detection_error(self, err_msg):
        QMessageBox.critical(self, "Detection Error", str(err_msg))
        self.set_processing_lock(False)
        self.update_window_title()

    def run_ocr_on_selected(self):
        if not self.current_image_path or not self.current_selected_box or not self.mocr_model: 
            return
        
        rect = self.current_selected_box.sceneBoundingRect()
        crop_rect = (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))
        
        self.set_processing_lock(True)
        self.update_window_title("Reading text...")
        self.ocr_input.setPlaceholderText("Reading text...")
        
        boxes_data = [(crop_rect, self.current_selected_box)]
        self.ocr_worker = BatchOCRWorker(self.mocr_model, self.current_image_path, boxes_data)
        self.ocr_worker.progress.connect(self.on_ocr_progress)
        self.ocr_worker.finished.connect(self.on_batch_ocr_finished)
        self.ocr_worker.start()

    def on_ocr_progress(self, text, box_item_ref):
        box_item_ref.raw_text = text
        if self.current_selected_box == box_item_ref:
            self._updating_ui = True
            self.ocr_input.setPlainText(text)
            self._updating_ui = False

    def on_batch_ocr_finished(self):
        self.set_processing_lock(False)
        self.update_window_title()