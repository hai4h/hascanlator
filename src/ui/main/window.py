import os
import psutil
from PySide6.QtGui import QFontDatabase, QDesktopServices, QFont, QColor, QShortcut, QKeySequence
from PySide6.QtCore import Qt, QRectF, Signal, QSettings, QTimer, QUrl
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QProgressBar, QLabel, QMenu, QWidgetAction, QCheckBox, QGraphicsScene
)

from src.core.workspace import WorkspaceManager
from src.ui.canvas.view import MangaCanvasView
from src.ui.canvas.items import BoundingBoxItem
from src.ui.settings.dialog import SettingsDialog
from src.ui.main.panels import EditorDockWidget, HistoryDockWidget
from src.ui.main.toolbar import MainToolbar
from src.ui.main.navigation import BottomNavigation
from src.ui.main.typeset import TypesetToolBar

# Mixins
from src.ui.main.mixins.image import ImageOperationsMixin
from src.ui.main.mixins.model import ModelManagementMixin
from src.ui.main.mixins.processing import WorkerProcessingMixin
from src.ui.main.mixins.shortcuts import ShortcutsMixin
from src.ui.main.mixins.fonts import FontManagementMixin
from src.ui.main.mixins.history import HistoryMixin
from src.ui.main.mixins.rendering import RenderingMixin

class HAScanlatorWindow(
    QMainWindow, ImageOperationsMixin, ModelManagementMixin, WorkerProcessingMixin,
    ShortcutsMixin, FontManagementMixin, HistoryMixin, RenderingMixin
):
    model_status_changed = Signal()

    def __init__(self):
        super().__init__()
        WorkerProcessingMixin.__init__(self) # Initialize worker tracking list
        RenderingMixin.__init__(self)
        self.setWindowTitle("HAScanlator")

        screen_geom = self.screen().availableGeometry()
        self.resize(int(screen_geom.width() * 0.75), int(screen_geom.height() * 0.75))

        self.settings = QSettings(os.path.join(os.getcwd(), "config.ini"), QSettings.IniFormat)
        self._initialize_config_defaults()

        if self.settings.value("use_hf_mirror", False, type=bool):
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

        self.workspace = WorkspaceManager()
        self.current_image_item = None
        self.current_selected_box = None
        self._updating_ui = False
        self.is_processing = False

        self.mocr_model, self.mocr_is_loading = None, False
        self.yolo_model, self.yolo_is_loading = None, False
        self.nmt_model, self.nmt_is_loading = None, False
        self.masking_model, self.masking_is_loading = None, False
        self.inpaint_model, self.inpaint_is_loading = None, False

        self.model_load_queue = []
        self.is_loading_model_seq = False
        self.loader_threads = []
        self.recent_fonts = []
        self.external_fonts = []
        self._orphaned_workers = []

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

        self._typeset_debounce = QTimer(self)
        self._typeset_debounce.setSingleShot(True)
        self._typeset_debounce.setInterval(80)
        self._typeset_debounce.timeout.connect(self._flush_typeset_update)

        self.update_window_title()
        self.update_button_states()
        self.reload_custom_fonts()
        QTimer.singleShot(500, self._auto_load_models_on_startup)

    def _auto_load_models_on_startup(self):
        if self.settings.value("auto_load_mocr", False, type=bool): self.load_model("manga_ocr")
        if self.settings.value("auto_load_yolo", False, type=bool): self.load_model("yolo_detector")
        if self.settings.value("auto_load_nmt", False, type=bool): self.load_model("nmt_translator")
        if self.settings.value("auto_load_masking", False, type=bool): self.load_model("masking_model")
        if self.settings.value("auto_load_inpaint", False, type=bool): self.load_model("inpaint_model")

    def _initialize_config_defaults(self):
        defaults = {
            "auto_load_mocr": False, "auto_load_yolo": False, "auto_load_nmt": False,
            "auto_load_masking": False, "auto_load_inpaint": False, "auto_process": False,
            "auto_scan_ocr": True, "auto_scan_translate": False, "auto_scan_mask": False,
            "auto_scan_inpaint": False, "auto_scan_typeset": False, "use_hf_mirror": False,
            "translation_engine": "google", "nmt_model_repo": "Helsinki-NLP/opus-mt-ja-en",
            "trans_src": "ja", "trans_tgt": "en", "default_font_family": "sans-serif",
            "default_font_size": 16, "default_font_bold": False, "default_font_italic": False,
            "default_font_underline": False, "default_font_strikeout": False, "default_align": "center",
            "default_indent": 5, "default_text_color": "black", "default_stroke_width": 0,
            "default_stroke_color": "white", "auto_stroke_size": 4,
            "auto_style_enabled": True, "auto_style_color": True, "auto_style_stroke": True,
            "typeset_toolbar_pos": "right",
            "ocr_allow_edit": False, "format_ellipsis_standard": True, "format_ellipsis_newline": True,
        }
        for key, val in defaults.items():
            if not self.settings.contains(key): self.settings.setValue(key, val)
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
        self.history_dock = HistoryDockWidget(self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.history_dock)

        center_area = QWidget()
        center_layout = QVBoxLayout(center_area)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.scene = QGraphicsScene()
        self.view = MangaCanvasView(self.scene)
        self.typeset_toolbar = TypesetToolBar(self.view)
        self.typeset_toolbar.setVisible(False)
        self.typeset_toolbar.position_requested.connect(self.set_typeset_toolbar_position)
        self.view.resized.connect(self.update_toolbar_geometry)
        self.view.verticalScrollBar().rangeChanged.connect(lambda min, max: self.update_toolbar_geometry())
        self.view.horizontalScrollBar().rangeChanged.connect(lambda min, max: self.update_toolbar_geometry())

        center_layout.addWidget(self.view, stretch=1)
        center_layout.addWidget(self.nav)

        initial_pos = self.settings.value("typeset_toolbar_pos", "right")
        self.set_typeset_toolbar_position(initial_pos)
        self.right_dock.ocr_input.setReadOnly(not self.settings.value("ocr_allow_edit", False, type=bool))

        main_layout.addWidget(self.toolbar)
        main_layout.addWidget(center_area, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.ram_lbl = QLabel("RAM: 0.00 GB")
        self.ram_lbl.setTextFormat(Qt.RichText)
        self.ram_lbl.setStyleSheet("padding-left: 10px; padding-right: 10px; color: #aaa;")
        self.statusBar().addPermanentWidget(self.ram_lbl)

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
        if hasattr(self.toolbar, 'btn_redo'):
            self.toolbar.btn_redo.clicked.connect(self.redo_edit)
        self.toolbar.btn_auto_detect.clicked.connect(self.run_auto_detect)
        self.toolbar.btn_add_box.clicked.connect(self.add_test_box)
        self.toolbar.btn_settings.clicked.connect(lambda: SettingsDialog(self).exec())
        self.toolbar.chk_auto_process.setChecked(self.settings.value("auto_process", False, type=bool))
        self.toolbar.chk_auto_process.stateChanged.connect(lambda: self.settings.setValue("auto_process", self.toolbar.chk_auto_process.isChecked()))

        # Auto-Scan Menu setup
        config_menu = QMenu(self.toolbar.btn_auto_scan_config)
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)
        config_layout.setContentsMargins(10, 10, 10, 10)
        config_layout.addWidget(QLabel("<b>Auto-Scan Pipeline</b>"))
        chk_ocr = QCheckBox("2. MangaOCR"); chk_ocr.setChecked(self.settings.value("auto_scan_ocr", True, type=bool))
        chk_trans = QCheckBox("3. Translate"); chk_trans.setChecked(self.settings.value("auto_scan_translate", False, type=bool))
        chk_mask = QCheckBox("4. Generate Text Mask"); chk_mask.setChecked(self.settings.value("auto_scan_mask", False, type=bool))
        chk_inpaint = QCheckBox("5. Inpaint Mask"); chk_inpaint.setChecked(self.settings.value("auto_scan_inpaint", False, type=bool))
        chk_typeset = QCheckBox("6. Typeset"); chk_typeset.setChecked(self.settings.value("auto_scan_typeset", False, type=bool))

        chk_ocr.toggled.connect(lambda v: self.settings.setValue("auto_scan_ocr", v))
        chk_trans.toggled.connect(lambda v: self._toggle_auto_scan_dep("auto_scan_translate", chk_ocr, v))
        chk_mask.toggled.connect(lambda v: self.settings.setValue("auto_scan_mask", v))
        chk_inpaint.toggled.connect(lambda v: self._toggle_auto_scan_dep("auto_scan_inpaint", chk_mask, v))
        chk_typeset.toggled.connect(lambda v: self._toggle_auto_scan_dep("auto_scan_typeset", chk_trans, v))

        for w in [chk_ocr, chk_trans, chk_mask, chk_inpaint, chk_typeset]: config_layout.addWidget(w)
        act = QWidgetAction(config_menu); act.setDefaultWidget(config_widget); config_menu.addAction(act)
        self.toolbar.btn_auto_scan_config.setMenu(config_menu)

        self.nav.btn_prev.clicked.connect(self.prev_image)
        self.nav.btn_next.clicked.connect(self.next_image)
        self.nav.page_jump_requested.connect(self.jump_to_image)

        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.right_dock.btn_run_ocr.clicked.connect(self.run_ocr_on_selected)
        self.right_dock.btn_delete_box.clicked.connect(self.delete_selected_box)
        self.right_dock.ocr_input.textChanged.connect(self.on_ocr_text_edited)
        self.right_dock.trans_input.textChanged.connect(self.on_trans_text_edited)
        self.right_dock.btn_translate_box.clicked.connect(self.run_translation_on_selected)
        self.right_dock.btn_trans_type_sel.clicked.connect(self.run_translate_typeset_selected)
        self.history_dock.history_list.itemClicked.connect(self.on_history_item_clicked)

        self.typeset_toolbar.btn_mask_bubble.clicked.connect(self.generate_bubble_mask)
        self.typeset_toolbar.btn_inpaint_bubble.clicked.connect(self.inpaint_bubble_mask)
        self.typeset_toolbar.btn_toggle_typeset.clicked.connect(self.toggle_typeset_view)
        self.typeset_toolbar.act_auto_fit.triggered.connect(self.auto_fit_selected_fonts)
        self.typeset_toolbar.act_set_fit_ratio.triggered.connect(self.set_auto_fit_ratio)

        self.typeset_toolbar.btn_align_left.clicked.connect(lambda: self.set_text_alignment(Qt.AlignLeft))
        self.typeset_toolbar.btn_align_center.clicked.connect(lambda: self.set_text_alignment(Qt.AlignCenter))
        self.typeset_toolbar.btn_align_right.clicked.connect(lambda: self.set_text_alignment(Qt.AlignRight))
        self.typeset_toolbar.btn_valign_top.clicked.connect(lambda: self.set_text_valignment(Qt.AlignTop))
        self.typeset_toolbar.btn_valign_middle.clicked.connect(lambda: self.set_text_valignment(Qt.AlignVCenter))
        self.typeset_toolbar.btn_valign_bottom.clicked.connect(lambda: self.set_text_valignment(Qt.AlignBottom))

        self.typeset_toolbar.btn_indent_plus.clicked.connect(lambda: self.set_text_indent(5))
        self.typeset_toolbar.btn_indent_minus.clicked.connect(lambda: self.set_text_indent(-5))
        self.typeset_toolbar.btn_line_space_plus.clicked.connect(lambda: self.set_text_line_spacing(0.1))
        self.typeset_toolbar.btn_line_space_minus.clicked.connect(lambda: self.set_text_line_spacing(-0.1))
        self.typeset_toolbar.btn_align_reset.clicked.connect(self.reset_text_alignment)
        self.typeset_toolbar.btn_spacing_reset.clicked.connect(self.reset_text_spacing)

        self.typeset_toolbar.btn_reload_fonts.clicked.connect(self.reload_custom_fonts)
        self.typeset_toolbar.btn_open_fonts.clicked.connect(lambda: self.open_settings(tab_index=2))
        self.typeset_toolbar.font_combo.currentIndexChanged.connect(self._on_font_combo_changed)
        self.typeset_toolbar.spin_size.valueChanged.connect(self.set_text_font_size_exact)
        self.typeset_toolbar.btn_size_plus.clicked.connect(lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() + 1))
        self.typeset_toolbar.btn_size_minus.clicked.connect(lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() - 1))
        self.typeset_toolbar.btn_bold.clicked.connect(self.toggle_text_bold)
        self.typeset_toolbar.btn_italic.clicked.connect(self.toggle_text_italic)
        self.typeset_toolbar.btn_underline.clicked.connect(self.toggle_text_underline)
        self.typeset_toolbar.btn_strike.clicked.connect(self.toggle_text_strikeout)
        self.typeset_toolbar.btn_font_reset.clicked.connect(self.reset_text_font)

        self.typeset_toolbar.combo_text_color.currentTextChanged.connect(self.set_text_color)
        self.typeset_toolbar.spin_stroke_width.valueChanged.connect(self.set_text_stroke_width)
        self.typeset_toolbar.btn_stroke_plus.clicked.connect(lambda: self.typeset_toolbar.spin_stroke_width.setValue(self.typeset_toolbar.spin_stroke_width.value() + 1))
        self.typeset_toolbar.btn_stroke_minus.clicked.connect(lambda: self.typeset_toolbar.spin_stroke_width.setValue(self.typeset_toolbar.spin_stroke_width.value() - 1))
        self.typeset_toolbar.combo_stroke_color.currentTextChanged.connect(self.set_text_stroke_color)

    def _toggle_auto_scan_dep(self, setting_key, prereq_chk, value):
        """Persists an Auto-Scan toggle, auto-enabling its prerequisite checkbox."""
        self.settings.setValue(setting_key, value)
        if value and not prereq_chk.isChecked():
            prereq_chk.setChecked(True)

    def closeEvent(self, event):
        """Safely terminates all threads and frees models before closing."""
        # Stop processing workers
        for w in list(self._active_workers):
            if w.isRunning():
                w.quit()
                w.wait(2000)
            w.deleteLater()
        self._active_workers.clear()

        # Stop model loaders
        for loader in self.loader_threads:
            if loader.isRunning():
                loader.quit()
                loader.wait(2000)
            loader.deleteLater()
        self.loader_threads.clear()

        # Stop orphaned background workers (font downloads, cache deletions)
        for worker in list(self._orphaned_workers):
            if worker.isRunning():
                worker.quit()
                worker.wait(2000)
            worker.deleteLater()
        self._orphaned_workers.clear()

        # Free models explicitly
        inp = getattr(self, "inpaint_model", None)
        if inp is not None:
            try:
                inp.close()
            except Exception:
                pass
        for key in ("mocr_model", "yolo_model", "nmt_model", "masking_model", "inpaint_model"):
            setattr(self, key, None)
        import gc; gc.collect()

        if self.scene: self.scene.clear()
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
        self.typeset_toolbar.set_position(pos)
        self.settings.setValue("typeset_toolbar_pos", pos)
        self.update_toolbar_geometry()

    def update_toolbar_geometry(self):
        if not hasattr(self, 'typeset_toolbar') or not self.view: return
        pos = self.settings.value("typeset_toolbar_pos", "right")
        vw, vh = self.view.width(), self.view.height()
        v_scroll = self.view.verticalScrollBar()
        v_width = v_scroll.width() if v_scroll.isVisible() else 0
        h_scroll = self.view.horizontalScrollBar()
        h_height = h_scroll.height() if h_scroll.isVisible() else 0
        tb_size = self.typeset_toolbar.sizeHint()

        if pos == "left": self.typeset_toolbar.setGeometry(0, 0, tb_size.width(), vh - h_height)
        elif pos == "right": self.typeset_toolbar.setGeometry(vw - tb_size.width() - v_width, 0, tb_size.width(), vh - h_height)
        elif pos == "top": self.typeset_toolbar.setGeometry(0, 0, vw - v_width, tb_size.height())
        elif pos == "bottom": self.typeset_toolbar.setGeometry(0, vh - tb_size.height() - h_height, vw - v_width, tb_size.height())

    def update_button_states(self):
        has_image = self.workspace.has_images
        selected_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        has_any_box = len(selected_boxes) > 0

        self.toolbar.btn_peek.setEnabled(has_image)
        path = self.workspace.current_image_path
        can_undo = has_image and path and path in self.workspace.history_indices and self.workspace.history_indices[path] > 0
        self.toolbar.btn_undo.setEnabled(can_undo)
        can_redo = has_image and path and path in self.workspace.history_indices and self.workspace.history_indices[path] < len(self.workspace.history.get(path, [])) - 1
        if hasattr(self.toolbar, 'btn_redo'): self.toolbar.btn_redo.setEnabled(can_redo)

        self.toolbar.btn_auto_detect.setEnabled(not self.is_processing and has_image)
        self.toolbar.btn_auto_detect.setText("Auto Detect\n(Whole Page)")
        self.right_dock.btn_run_ocr.setEnabled(not self.is_processing and has_image and has_any_box)
        self.right_dock.btn_translate_box.setEnabled(not self.is_processing and has_image and has_any_box)
        self.right_dock.btn_trans_type_sel.setEnabled(not self.is_processing and has_image and has_any_box)
        self.right_dock.btn_delete_box.setEnabled(has_any_box)
        self.typeset_toolbar.setEnabled(not self.is_processing)
        self.nav.btn_prev.setEnabled(not self.is_processing and self.workspace.current_img_index > 0)
        self.nav.btn_next.setEnabled(not self.is_processing and self.workspace.current_img_index < self.workspace.total_pages - 1)

    def _update_ram_usage(self):
        try:
            process = psutil.Process(os.getpid())
            app_gb = process.memory_info().rss / (1024 ** 3)
            vm = psutil.virtual_memory()
            sys_used_gb = (vm.total - vm.available) / (1024 ** 3)
            sys_total_gb = vm.total / (1024 ** 3)
            self.ram_lbl.setText(
                f"RAM: <font color='#5cb85c'><b>{app_gb:.2f} GB</b></font> (App)  |  "
                f"<font color='#f0ad4e'><b>{sys_used_gb:.2f} GB</b></font> / "
                f"<font color='#5bc0de'><b>{sys_total_gb:.1f} GB</b></font> (System)"
            )
        except Exception: pass

    def set_processing_lock(self, locked):
        self.is_processing = locked
        self.update_button_states()

    def on_selection_changed(self):
        boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        dock = self.right_dock
        self.typeset_toolbar.setVisible(len(boxes) > 0)

        if len(boxes) == 1:
            self.current_selected_box = boxes[0]
            self._updating_ui = True
            dock.ocr_input.setEnabled(True); dock.trans_input.setEnabled(True)
            dock.ocr_input.setPlainText(self.current_selected_box.raw_text)
            dock.trans_input.setPlainText(self.current_selected_box.translated_text)
            self.refresh_font_combo(self.current_selected_box.font_family)

            self.typeset_toolbar.spin_size.blockSignals(True)
            self.typeset_toolbar.spin_size.setValue(self.current_selected_box.font_size)
            self.typeset_toolbar.spin_size.blockSignals(False)
            self._updating_ui = False
        else:
            self.current_selected_box = None
            self._updating_ui = True
            dock.ocr_input.clear(); dock.trans_input.clear()
            dock.ocr_input.setEnabled(False); dock.trans_input.setEnabled(False)
            if len(boxes) > 1:
                dock.ocr_input.setPlaceholderText(f"{len(boxes)} boxes selected.")
                dock.trans_input.setPlaceholderText(f"{len(boxes)} boxes selected.")
            else:
                dock.ocr_input.setPlaceholderText(""); dock.trans_input.setPlaceholderText("")
            self._updating_ui = False
        self.update_button_states()

    def on_ocr_text_edited(self):
        if not self._updating_ui and self.current_selected_box:
            self.current_selected_box.raw_text = self.right_dock.ocr_input.toPlainText()

    def on_trans_text_edited(self):
        if not self._updating_ui and self.current_selected_box:
            self.current_selected_box.translated_text = self.right_dock.trans_input.toPlainText()
            if self.current_selected_box.is_typeset:
                self._typeset_debounce.start()

    def _flush_typeset_update(self):
        if self.current_selected_box and self.current_selected_box.is_typeset:
            self.current_selected_box.update_typeset()

    def select_all_boxes(self):
        for item in self.scene.items():
            if isinstance(item, BoundingBoxItem): item.setSelected(True)

    def add_test_box(self):
        if not self.current_image_item: return
        center = self.view.mapToScene(self.view.viewport().rect().center())
        box = BoundingBoxItem(QRectF(center.x() - 50, center.y() - 100, 100, 200), is_auto=False)
        self.apply_default_font_settings(box)
        self.scene.addItem(box)
        self.scene.clearSelection()
        box.setSelected(True)
        self.commit_history("Add Box (Manual)")

    def delete_selected_box(self):
        count = 0
        for item in self.scene.selectedItems():
            if isinstance(item, BoundingBoxItem):
                self.scene.removeItem(item)
                count += 1
        if count > 0: self.commit_history(f"Delete {count} Box(es)")

    def open_settings(self, tab_index=0):
        dialog = SettingsDialog(self)
        dialog.tabs.setCurrentIndex(tab_index)
        dialog.exec()
