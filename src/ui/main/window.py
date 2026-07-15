import os
import psutil

from PySide6.QtGui import QPixmap, QFontDatabase, QDesktopServices, QFont, QColor
from PySide6.QtCore import Qt, QRectF, Signal, QSettings, QTimer, QUrl
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGraphicsScene, QGraphicsPixmapItem, QFileDialog, QProgressBar, QLabel
)

from src.core.workspace import WorkspaceManager

from src.ui.canvas.view import MangaCanvasView
from src.ui.canvas.items import BoundingBoxItem

from src.ui.settings.dialog import SettingsDialog

from src.ui.main.panels import EditorDockWidget
from src.ui.main.toolbar import MainToolbar
from src.ui.main.navigation import BottomNavigation
from src.ui.main.typeset import TypesetToolBar

from src.ui.main.mixins.image import ImageOperationsMixin
from src.ui.main.mixins.model import ModelManagementMixin
from src.ui.main.mixins.processing import WorkerProcessingMixin

class HAScanlatorWindow(QMainWindow, ImageOperationsMixin, ModelManagementMixin, WorkerProcessingMixin):
    model_status_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HAScanlator")
        self.resize(1300, 800)
        
        config_path = os.path.join(os.getcwd(), "config.ini")
        self.settings = QSettings(config_path, QSettings.IniFormat)
        # populate config.ini with all defaults immediately
        self._initialize_config_defaults()
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

        self.recent_fonts = []
        self.external_fonts = []

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

        # Load local fonts on boot
        self.reload_custom_fonts()

    def _initialize_config_defaults(self):
        """Populates config.ini with all default settings so they are visible and editable by the user."""
        defaults = {
            "auto_load_mocr": False,
            "auto_load_yolo": False,
            "auto_load_nmt": False,
            "auto_process": False,  # Auto-Scan in UI
            "translation_engine": "google",
            "nmt_model_repo": "Helsinki-NLP/opus-mt-ja-en",
            "trans_src": "ja",
            "trans_tgt": "en",
            "default_font_family": "sans-serif",
            "default_font_size": 16,
            "default_font_bold": False,
            "default_font_italic": False,
            "default_font_underline": False,
            "default_font_strikeout": False,
            "typeset_toolbar_pos": "right"
        }
        
        for key, default_val in defaults.items():
            if not self.settings.contains(key):
                self.settings.setValue(key, default_val)
                
        self.settings.sync()

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
        center_layout.setSpacing(0)
        
        self.scene = QGraphicsScene()
        self.view = MangaCanvasView(self.scene)
        
        # Parent the toolbar directly to the view so it acts as an overlay layer ON TOP of the canvas
        self.typeset_toolbar = TypesetToolBar(self.view) 
        self.typeset_toolbar.setVisible(False) 
        self.typeset_toolbar.position_requested.connect(self.set_typeset_toolbar_position)
        
        # Connect the canvas resize event so the overlay sticks tightly to the edges
        self.view.resized.connect(self.update_toolbar_geometry)
        
        center_layout.addWidget(self.view, stretch=1)
        center_layout.addWidget(self.nav)
        
        # Apply initial position from settings
        initial_pos = self.settings.value("typeset_toolbar_pos", "right")
        self.set_typeset_toolbar_position(initial_pos)
        
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
        
        # --- TYPESET SIGNALS ---
        self.typeset_toolbar.btn_clean_bubble.clicked.connect(self.smart_clean_bubble)
        self.typeset_toolbar.btn_toggle_typeset.clicked.connect(self.toggle_typeset_view)
        
        # --- TEXT ALIGN SIGNALS ---
        self.typeset_toolbar.btn_align_left.clicked.connect(lambda: self.set_text_alignment(Qt.AlignLeft))
        self.typeset_toolbar.btn_align_center.clicked.connect(lambda: self.set_text_alignment(Qt.AlignCenter))
        self.typeset_toolbar.btn_align_right.clicked.connect(lambda: self.set_text_alignment(Qt.AlignRight))
        self.typeset_toolbar.btn_valign_top.clicked.connect(lambda: self.set_text_valignment(Qt.AlignTop))
        self.typeset_toolbar.btn_valign_middle.clicked.connect(lambda: self.set_text_valignment(Qt.AlignVCenter))
        self.typeset_toolbar.btn_valign_bottom.clicked.connect(lambda: self.set_text_valignment(Qt.AlignBottom))
        
        # --- TEXT INDENT SIGNALS ---
        self.typeset_toolbar.btn_indent_plus.clicked.connect(lambda: self.set_text_indent(5))
        self.typeset_toolbar.btn_indent_minus.clicked.connect(lambda: self.set_text_indent(-5))
        self.typeset_toolbar.btn_line_space_plus.clicked.connect(lambda: self.set_text_line_spacing(0.1))
        self.typeset_toolbar.btn_line_space_minus.clicked.connect(lambda: self.set_text_line_spacing(-0.1))
        self.typeset_toolbar.btn_align_reset.clicked.connect(self.reset_text_alignment)
        self.typeset_toolbar.btn_spacing_reset.clicked.connect(self.reset_text_spacing)

        # --- FONT SIGNALS ---
        self.typeset_toolbar.btn_reload_fonts.clicked.connect(self.reload_custom_fonts)
        self.typeset_toolbar.btn_open_fonts.clicked.connect(lambda: self.open_settings(tab_index=2))
        self.typeset_toolbar.font_combo.currentIndexChanged.connect(self._on_font_combo_changed)
        
        self.typeset_toolbar.spin_size.valueChanged.connect(self.set_text_font_size_exact)
        
        self.typeset_toolbar.btn_size_plus.clicked.connect(
            lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() + 1)
        )
        self.typeset_toolbar.btn_size_minus.clicked.connect(
            lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() - 1)
        )
        
        self.typeset_toolbar.btn_bold.clicked.connect(self.toggle_text_bold)
        self.typeset_toolbar.btn_italic.clicked.connect(self.toggle_text_italic)
        self.typeset_toolbar.btn_underline.clicked.connect(self.toggle_text_underline)
        self.typeset_toolbar.btn_strike.clicked.connect(self.toggle_text_strikeout)
        self.typeset_toolbar.btn_font_reset.clicked.connect(self.reset_text_font)

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

    def set_typeset_toolbar_position(self, pos):
        """Updates the orientation and triggers a geometry update."""
        self.typeset_toolbar.set_position(pos)
        self.settings.setValue("typeset_toolbar_pos", pos)
        self.update_toolbar_geometry()
        
    def update_toolbar_geometry(self):
        """Pins the overlay toolbar to the exact inner edges of the canvas view."""
        if not hasattr(self, 'typeset_toolbar') or not self.view: return
        
        pos = self.settings.value("typeset_toolbar_pos", "right")
        vw = self.view.width()
        vh = self.view.height()
        
        # Calculate absolute pixel coordinates for the overlay relative to the canvas inner walls
        if pos == "left":
            self.typeset_toolbar.setGeometry(0, 0, 50, vh)
        elif pos == "right":
            self.typeset_toolbar.setGeometry(vw - 50, 0, 50, vh)
        elif pos == "top":
            self.typeset_toolbar.setGeometry(0, 0, vw, 50)
        elif pos == "bottom":
            self.typeset_toolbar.setGeometry(0, vh - 50, vw, 50)

    def update_button_states(self):
        has_image = self.workspace.has_images
        selected_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        has_any_box = len(selected_boxes) > 0
        engine = self.settings.value("translation_engine", "google")
        
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
            self.right_dock.btn_run_ocr.setEnabled(not self.is_processing and has_image and has_any_box)
            self.right_dock.btn_run_ocr.setText("Run OCR on Selected")
        
        if engine == "nmt" and self.nmt_model is None:
            self.right_dock.btn_translate_box.setEnabled(False)
            self.right_dock.btn_translate_box.setText("NMT Model Required")
            self.right_dock.btn_translate_all.setEnabled(False)
        else:
            self.right_dock.btn_translate_box.setEnabled(not self.is_processing and has_image and has_any_box)
            self.right_dock.btn_translate_box.setText("Translate Selected")
            self.right_dock.btn_translate_all.setEnabled(not self.is_processing and has_image)
            
        self.right_dock.btn_delete_box.setEnabled(has_any_box)
        
        # Lock contextual toolbar if scanning is happening
        self.typeset_toolbar.setEnabled(not self.is_processing)
            
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

        cached_data = self.workspace.get_page_state(path)
        if cached_data:
            for b_data in cached_data:
                box = BoundingBoxItem(b_data['rect'], is_auto=b_data['is_auto'])
                box.setPos(b_data['pos'])
                box.raw_text, box.translated_text = b_data['raw_text'], b_data['translated_text']

                box.align = b_data.get('align', Qt.AlignCenter)
                box.valign = b_data.get('valign', Qt.AlignVCenter) 
                box.indent = b_data.get('indent', 5)
                box.line_spacing = b_data.get('line_spacing', 1.0)
                
                box.font_family = b_data.get('font_family', "sans-serif")
                box.font_size = b_data.get('font_size', 16)
                box.is_bold = b_data.get('is_bold', False)
                box.is_italic = b_data.get('is_italic', False)
                box.is_underline = b_data.get('is_underline', False)
                box.is_strikeout = b_data.get('is_strikeout', False)
                
                self.scene.addItem(box)
                
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
            'valign': getattr(item, 'valign', Qt.AlignVCenter), 
            'indent': getattr(item, 'indent', 5),
            'line_spacing': getattr(item, 'line_spacing', 1.0),
            'font_family': getattr(item, 'font_family', "sans-serif"),
            'font_size': getattr(item, 'font_size', 16),
            'is_bold': getattr(item, 'is_bold', False),
            'is_italic': getattr(item, 'is_italic', False),
            'is_underline': getattr(item, 'is_underline', False),
            'is_strikeout': getattr(item, 'is_strikeout', False)
            
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

    def on_selection_changed(self):
        boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        dock = self.right_dock
        
        # --- CONTROL CONTEXT TOOLBAR VISIBILITY ---
        has_any_box = len(boxes) > 0
        self.typeset_toolbar.setVisible(has_any_box)
        
        if len(boxes) == 1:
            self.current_selected_box = boxes[0]
            self._updating_ui = True 
            dock.ocr_input.setEnabled(True)
            dock.trans_input.setEnabled(True)
            dock.ocr_input.setPlainText(self.current_selected_box.raw_text)
            dock.trans_input.setPlainText(self.current_selected_box.translated_text)
            
            # --- SYNC FONT UI ---
            self.refresh_font_combo(self.current_selected_box.font_family)
            
            self.typeset_toolbar.spin_size.blockSignals(True)
            self.typeset_toolbar.spin_size.setValue(self.current_selected_box.font_size)
            self.typeset_toolbar.spin_size.blockSignals(False)
            
            self._updating_ui = False 
        else:
            self.current_selected_box = None
            self._updating_ui = True
            dock.ocr_input.clear()
            dock.trans_input.clear()
            dock.ocr_input.setEnabled(False)
            dock.trans_input.setEnabled(False)
            
            if len(boxes) > 1:
                dock.ocr_input.setPlaceholderText(f"{len(boxes)} boxes selected.")
                dock.trans_input.setPlaceholderText(f"{len(boxes)} boxes selected.")
            else:
                dock.ocr_input.setPlaceholderText("")
                dock.trans_input.setPlaceholderText("")
                
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
        self.apply_default_font_settings(box)
        self.scene.addItem(box)
        self.scene.clearSelection()
        box.setSelected(True)

    def delete_selected_box(self):
        for item in self.scene.selectedItems():
            if isinstance(item, BoundingBoxItem):
                self.scene.removeItem(item)

    # --- FONT MANAGEMENT ---
    def open_settings(self, tab_index=0):
        dialog = SettingsDialog(self)
        dialog.tabs.setCurrentIndex(tab_index)
        dialog.exec()

    def reload_custom_fonts(self):
        fonts_dir = os.path.join(os.getcwd(), "fonts")
        os.makedirs(fonts_dir, exist_ok=True)
        
        self.external_fonts = []
        loaded = 0
        
        # Traverse all directories and subdirectories inside /fonts
        for root, _, files in os.walk(fonts_dir):
            for filename in files:
                if filename.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
                    font_path = os.path.join(root, filename)
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    if font_id != -1:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        for family in families:
                            if family not in self.external_fonts:
                                self.external_fonts.append(family)
                        loaded += 1
                        
        if loaded > 0:
            self.statusBar().showMessage(f"Loaded {loaded} custom font(s) from local folders.")
        self.refresh_font_combo()

    def refresh_font_combo(self, current_font=None):
        """Builds a custom hierarchical font list: Current -> Recent -> External -> All"""
        combo = self.typeset_toolbar.font_combo
        combo.blockSignals(True)
        combo.clear()

        all_fonts = QFontDatabase.families()

        def add_header(text):
            combo.addItem(text)
            idx = combo.count() - 1
            model = combo.model()
            item = model.item(idx)
            if item:
                item.setEnabled(False)
                item.setBackground(QColor("#333333"))
                item.setForeground(QColor("#aaaaaa"))
                f = item.font()
                f.setBold(True)
                item.setFont(f)

        def add_font_item(family):
            combo.addItem(family)
            idx = combo.count() - 1
            combo.setItemData(idx, family, Qt.UserRole) 
            combo.setItemData(idx, QFont(family), Qt.FontRole) 

        if current_font:
            add_header("--- CURRENT ---")
            add_font_item(current_font)

        if self.recent_fonts:
            add_header("--- RECENT ---")
            for f in self.recent_fonts: add_font_item(f)

        if self.external_fonts:
            add_header("--- EXTERNAL ---")
            for f in self.external_fonts: add_font_item(f)

        add_header("--- ALL FONTS ---")
        for f in all_fonts: add_font_item(f)

        if current_font:
            combo.setCurrentIndex(1) 
            
        combo.blockSignals(False)

    def _on_font_combo_changed(self, index):
        family = self.typeset_toolbar.font_combo.itemData(index, Qt.UserRole)
        if family: 
            self.set_text_font_family(family)