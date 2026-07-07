import os
import psutil

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGraphicsScene, QGraphicsPixmapItem, QFileDialog, QProgressBar, QLabel
)
from PySide6.QtCore import Qt, QRectF, Signal, QSettings, QTimer

from src.core.workspace import WorkspaceManager

from src.ui.canvas.view import MangaCanvasView
from src.ui.canvas.items import BoundingBoxItem

from src.ui.settings.dialog import SettingsDialog

from src.ui.main.panels import EditorDockWidget
from src.ui.main.toolbar import MainToolbar
from src.ui.main.navigation import BottomNavigation

from src.ui.main.mixins.image_mixin import ImageOperationsMixin
from src.ui.main.mixins.model_mixin import ModelManagementMixin
from src.ui.main.mixins.processing_mixin import WorkerProcessingMixin

class HAScanlatorWindow(QMainWindow, ImageOperationsMixin, ModelManagementMixin, WorkerProcessingMixin):
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