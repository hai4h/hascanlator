import os
import psutil

from PySide6.QtGui import QPixmap, QFontDatabase, QDesktopServices, QFont, QColor, QShortcut, QKeySequence
from PySide6.QtCore import Qt, QRectF, Signal, QSettings, QTimer, QUrl
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsScene, QGraphicsPixmapItem, QFileDialog, QProgressBar, QLabel
)

from src.core.workspace import WorkspaceManager

from src.ui.canvas.view import MangaCanvasView
from src.ui.canvas.items import BoundingBoxItem

from src.ui.settings.dialog import SettingsDialog

from src.ui.main.panels import EditorDockWidget, HistoryDockWidget
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

        # Scale dynamically to 75% of the user's screen space
        screen_geom = self.screen().availableGeometry()
        self.resize(int(screen_geom.width() * 0.75), int(screen_geom.height() * 0.75))

        config_path = os.path.join(os.getcwd(), "config.ini")
        self.settings = QSettings(config_path, QSettings.IniFormat)
        # populate config.ini with all defaults immediately
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
        self.ocr_worker = None
        self.detect_worker = None
        self.translation_worker = None

        self.recent_fonts = []
        self.external_fonts = []

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

        self.update_window_title()
        self.update_button_states()

        # Load local fonts on boot
        self.reload_custom_fonts()

        # Delay auto-loading models by 500ms to ensure the main window renders first
        QTimer.singleShot(500, self._auto_load_models_on_startup)

    def _auto_load_models_on_startup(self):
        if self.settings.value("auto_load_mocr", False, type=bool):
            self.load_model("manga_ocr")
        if self.settings.value("auto_load_yolo", False, type=bool):
            self.load_model("yolo_detector")
        if self.settings.value("auto_load_nmt", False, type=bool):
            self.load_model("nmt_translator")
        if self.settings.value("auto_load_masking", False, type=bool):
            self.load_model("masking_model")
        if self.settings.value("auto_load_inpaint", False, type=bool):
            self.load_model("inpaint_model")

    def _initialize_config_defaults(self):
        """Populates config.ini with all default settings so they are visible and editable by the user."""
        defaults = {
            "auto_load_mocr": False,
            "auto_load_yolo": False,
            "auto_load_nmt": False,
            "auto_load_masking": False,
            "auto_load_inpaint": False,
            "auto_process": False,
            "auto_scan_ocr": True,
            "auto_scan_translate": False,
            "auto_scan_mask": False,
            "auto_scan_inpaint": False,
            "auto_scan_typeset": False,
            "use_hf_mirror": False,
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
            "default_align": "center",
            "default_indent": 5,
            "default_text_color": "black",
            "default_stroke_width": 0,
            "default_stroke_color": "white",
            "typeset_toolbar_pos": "right",
            "ocr_allow_edit": False,
            "format_ellipsis_standard": True,
            "format_ellipsis_newline": True,

            # Keybind Defaults
            "keybind_select_all": "Ctrl+A",
            "keybind_delete_box": "Del",
            "keybind_load_images": "",
            "keybind_reset_workspace": "",
            "keybind_open_settings": "",
            "keybind_next_page": "",
            "keybind_prev_page": "",
            "keybind_add_box": "",
            "keybind_undo_edit": "",
            "keybind_redo_edit": "",
            "keybind_auto_detect": "",
            "keybind_run_ocr": "",
            "keybind_translate_box": "",
            "keybind_trans_type_sel": "",
            "keybind_trans_type_all": "",
            "keybind_generate_mask": "",
            "keybind_inpaint_bubble": "",
            "keybind_toggle_typeset": "",
            "keybind_bold": "",
            "keybind_italic": "",
            "keybind_underline": "",
            "keybind_strikeout": "",
            "keybind_align_left": "",
            "keybind_align_center": "",
            "keybind_align_right": "",
            "keybind_font_up": "",
            "keybind_font_down": "",
            "keybind_line_space_up": "",
            "keybind_line_space_down": "",
            "keybind_indent_up": "",
            "keybind_indent_down": ""
        }

        for key, default_val in defaults.items():
            if not self.settings.contains(key):
                self.settings.setValue(key, default_val)

        self.settings.sync()

    def _setup_shortcuts(self):
        self.shortcuts = {}

        bindings = [
            ("keybind_load_images", self.load_images_dialog),
            ("keybind_reset_workspace", self.reset_workspace),
            ("keybind_open_settings", lambda: self.open_settings()),
            ("keybind_next_page", self.next_image),
            ("keybind_prev_page", self.prev_image),
            ("keybind_select_all", self.select_all_boxes),
            ("keybind_delete_box", self.delete_selected_box),
            ("keybind_add_box", self.add_test_box),
            ("keybind_undo_edit", self.undo_edit),
            ("keybind_redo_edit", self.redo_edit),
            ("keybind_auto_detect", self.run_auto_detect),
            ("keybind_run_ocr", self.run_ocr_on_selected),
            ("keybind_translate_box", self.run_translation_on_selected),
            ("keybind_trans_type_sel", self.run_translate_typeset_selected),
            ("keybind_trans_type_all", self.run_translate_typeset_all),
            ("keybind_generate_mask", self.generate_bubble_mask),
            ("keybind_inpaint_bubble", self.inpaint_bubble_mask),
            ("keybind_toggle_typeset", self.toggle_typeset_view),
            ("keybind_bold", self.toggle_text_bold),
            ("keybind_italic", self.toggle_text_italic),
            ("keybind_underline", self.toggle_text_underline),
            ("keybind_strikeout", self.toggle_text_strikeout),
            ("keybind_align_left", lambda: self.set_text_alignment(Qt.AlignLeft)),
            ("keybind_align_center", lambda: self.set_text_alignment(Qt.AlignCenter)),
            ("keybind_align_right", lambda: self.set_text_alignment(Qt.AlignRight)),
            ("keybind_font_up", lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() + 1)),
            ("keybind_font_down", lambda: self.typeset_toolbar.spin_size.setValue(self.typeset_toolbar.spin_size.value() - 1)),
            ("keybind_line_space_up", lambda: self.set_text_line_spacing(0.1)),
            ("keybind_line_space_down", lambda: self.set_text_line_spacing(-0.1)),
            ("keybind_indent_up", lambda: self.set_text_indent(5)),
            ("keybind_indent_down", lambda: self.set_text_indent(-5)),
        ]

        for key, func in bindings:
            sc = QShortcut(self.view)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(func)
            self.shortcuts[key] = sc

        self.reload_shortcuts()

    def reload_shortcuts(self):
        # 1. Tally all configured keybinds
        seq_counts = {}
        for key in self.shortcuts.keys():
            default_val = "Ctrl+A" if key == "keybind_select_all" else "Del" if key == "keybind_delete_box" else ""
            val = self.settings.value(key, default_val)
            if val:
                seq_counts[val] = seq_counts.get(val, 0) + 1

        # 2. Only apply shortcuts that are completely unique (no duplicates)
        for key, sc in self.shortcuts.items():
            default_val = "Ctrl+A" if key == "keybind_select_all" else "Del" if key == "keybind_delete_box" else ""
            val = self.settings.value(key, default_val)

            if val and seq_counts.get(val, 0) == 1:
                sc.setKey(QKeySequence(val))
                sc.setEnabled(True)
            else:
                sc.setKey(QKeySequence()) # Safely disable if empty or duplicated
                sc.setEnabled(False)

    def select_all_boxes(self):
        for item in self.scene.items():
            if isinstance(item, BoundingBoxItem):
                item.setSelected(True)

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

        # Parent the toolbar directly to the view so it acts as an overlay layer ON TOP of the canvas
        self.typeset_toolbar = TypesetToolBar(self.view)
        self.typeset_toolbar.setVisible(False)
        self.typeset_toolbar.position_requested.connect(self.set_typeset_toolbar_position)

        # Connect the canvas resize event so the overlay sticks tightly to the edges
        self.view.resized.connect(self.update_toolbar_geometry)
        
        # Also connect scrollbar visibility changes so it doesn't overlap them when zooming
        self.view.verticalScrollBar().rangeChanged.connect(lambda min, max: self.update_toolbar_geometry())
        self.view.horizontalScrollBar().rangeChanged.connect(lambda min, max: self.update_toolbar_geometry())

        center_layout.addWidget(self.view, stretch=1)
        center_layout.addWidget(self.nav)

        # Apply initial position from settings
        initial_pos = self.settings.value("typeset_toolbar_pos", "right")
        self.set_typeset_toolbar_position(initial_pos)

        # Apply OCR edit lock setting
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
        self.toolbar.chk_auto_process.stateChanged.connect(
            lambda: self.settings.setValue("auto_process", self.toolbar.chk_auto_process.isChecked())
        )

        # --- AUTO-SCAN CONFIGURATION MENU ---
        from PySide6.QtWidgets import QMenu, QWidgetAction, QVBoxLayout, QCheckBox
        config_menu = QMenu(self.toolbar.btn_auto_scan_config)
        config_menu.setStyleSheet("QMenu { border: 1px solid #555; background-color: #2b2b2b; }")
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)
        config_layout.setContentsMargins(10, 10, 10, 10)
        config_layout.setSpacing(6)

        config_layout.addWidget(QLabel("<b>Auto-Scan Pipeline</b>"))

        chk_yolo = QCheckBox("1. YOLO Detection")
        chk_yolo.setChecked(True)
        chk_yolo.setEnabled(False)

        chk_ocr = QCheckBox("2. MangaOCR")
        chk_ocr.setChecked(self.settings.value("auto_scan_ocr", True, type=bool))

        chk_trans = QCheckBox("3. Translate")
        chk_trans.setChecked(self.settings.value("auto_scan_translate", False, type=bool))

        chk_mask = QCheckBox("4. Generate Text Mask")
        chk_mask.setChecked(self.settings.value("auto_scan_mask", False, type=bool))

        chk_inpaint = QCheckBox("5. Inpaint Mask")
        chk_inpaint.setChecked(self.settings.value("auto_scan_inpaint", False, type=bool))

        chk_typeset = QCheckBox("6. Typeset")
        chk_typeset.setChecked(self.settings.value("auto_scan_typeset", False, type=bool))

        config_layout.addWidget(chk_yolo)
        config_layout.addWidget(chk_ocr)
        config_layout.addWidget(chk_trans)
        config_layout.addWidget(chk_mask)
        config_layout.addWidget(chk_inpaint)
        config_layout.addWidget(chk_typeset)

        # Enforce Logical Dependencies visually
        def on_trans_toggled(v):
            self.settings.setValue("auto_scan_translate", v)
            if v and not chk_ocr.isChecked(): chk_ocr.setChecked(True)

        def on_inpaint_toggled(v):
            self.settings.setValue("auto_scan_inpaint", v)
            if v and not chk_mask.isChecked(): chk_mask.setChecked(True)

        def on_type_toggled(v):
            self.settings.setValue("auto_scan_typeset", v)
            if v and not chk_trans.isChecked(): chk_trans.setChecked(True)

        chk_ocr.toggled.connect(lambda v: self.settings.setValue("auto_scan_ocr", v))
        chk_trans.toggled.connect(on_trans_toggled)
        chk_mask.toggled.connect(lambda v: self.settings.setValue("auto_scan_mask", v))
        chk_inpaint.toggled.connect(on_inpaint_toggled)
        chk_typeset.toggled.connect(on_type_toggled)
        act = QWidgetAction(config_menu)
        act.setDefaultWidget(config_widget)
        config_menu.addAction(act)
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
        self.right_dock.btn_trans_type_all.clicked.connect(self.run_translate_typeset_all)

        self.history_dock.history_list.itemClicked.connect(self.on_history_item_clicked)

        # --- TYPESET SIGNALS ---
        self.typeset_toolbar.btn_mask_bubble.clicked.connect(self.generate_bubble_mask)
        self.typeset_toolbar.btn_inpaint_bubble.clicked.connect(self.inpaint_bubble_mask)
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

        # --- STROKE & COLOR SIGNALS ---
        self.typeset_toolbar.combo_text_color.currentTextChanged.connect(self.set_text_color)
        
        self.typeset_toolbar.spin_stroke_width.valueChanged.connect(self.set_text_stroke_width)
        self.typeset_toolbar.btn_stroke_plus.clicked.connect(
            lambda: self.typeset_toolbar.spin_stroke_width.setValue(self.typeset_toolbar.spin_stroke_width.value() + 1)
        )
        self.typeset_toolbar.btn_stroke_minus.clicked.connect(
            lambda: self.typeset_toolbar.spin_stroke_width.setValue(self.typeset_toolbar.spin_stroke_width.value() - 1)
        )
        self.typeset_toolbar.combo_stroke_color.currentTextChanged.connect(self.set_text_stroke_color)

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

        # Safely account for scrollbars so the toolbar doesn't hide underneath them
        v_scroll = self.view.verticalScrollBar()
        v_width = v_scroll.width() if v_scroll.isVisible() else 0
        
        h_scroll = self.view.horizontalScrollBar()
        h_height = h_scroll.height() if h_scroll.isVisible() else 0

        # Calculate absolute pixel coordinates based on dynamic content size rather than a fixed 50px
        tb_size = self.typeset_toolbar.sizeHint()

        if pos == "left":
            self.typeset_toolbar.setGeometry(0, 0, tb_size.width(), vh - h_height)
        elif pos == "right":
            self.typeset_toolbar.setGeometry(vw - tb_size.width() - v_width, 0, tb_size.width(), vh - h_height)
        elif pos == "top":
            self.typeset_toolbar.setGeometry(0, 0, vw - v_width, tb_size.height())
        elif pos == "bottom":
            self.typeset_toolbar.setGeometry(0, vh - tb_size.height() - h_height, vw - v_width, tb_size.height())

    def update_button_states(self):
        has_image = self.workspace.has_images
        selected_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        has_any_box = len(selected_boxes) > 0
        engine = self.settings.value("translation_engine", "google")

        # Toolbar State
        self.toolbar.btn_peek.setEnabled(has_image)

        path = self.workspace.current_image_path

        can_undo = has_image and path and path in self.workspace.history_indices and self.workspace.history_indices[path] > 0
        self.toolbar.btn_undo.setEnabled(can_undo)

        can_redo = has_image and path and path in self.workspace.history_indices and self.workspace.history_indices[path] < len(self.workspace.history.get(path, [])) - 1
        if hasattr(self.toolbar, 'btn_redo'):
            self.toolbar.btn_redo.setEnabled(can_redo)

        self.toolbar.btn_auto_detect.setEnabled(not self.is_processing and has_image)
        self.toolbar.btn_auto_detect.setText("Auto Detect\n(Whole Page)")

        # OCR / Trans State
        self.right_dock.btn_run_ocr.setEnabled(not self.is_processing and has_image and has_any_box)

        self.right_dock.btn_translate_box.setEnabled(not self.is_processing and has_image and has_any_box)
        self.right_dock.btn_trans_type_sel.setEnabled(not self.is_processing and has_image and has_any_box)
        self.right_dock.btn_trans_type_all.setEnabled(not self.is_processing and has_image)

        self.right_dock.btn_delete_box.setEnabled(has_any_box)

        # Lock contextual toolbar if scanning is happening
        self.typeset_toolbar.setEnabled(not self.is_processing)

        # Navigation
        self.nav.btn_prev.setEnabled(not self.is_processing and self.workspace.current_img_index > 0)
        self.nav.btn_next.setEnabled(not self.is_processing and self.workspace.current_img_index < self.workspace.total_pages - 1)

    def _update_ram_usage(self):
        try:
            process = psutil.Process(os.getpid())
            app_gb = process.memory_info().rss / (1024 ** 3)

            vm = psutil.virtual_memory()
            # (total - available) is a cross-platform reliable way to get actual used RAM
            sys_used_gb = (vm.total - vm.available) / (1024 ** 3)
            sys_total_gb = vm.total / (1024 ** 3)

            # Colors: Green for App, Orange for System Used, Light Blue for System Total
            self.ram_lbl.setText(
                f"RAM: <font color='#5cb85c'><b>{app_gb:.2f} GB</b></font> (App)  |  "
                f"<font color='#f0ad4e'><b>{sys_used_gb:.2f} GB</b></font> / "
                f"<font color='#5bc0de'><b>{sys_total_gb:.1f} GB</b></font> (System)"
            )
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
        self.history_dock.history_list.clear()
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
            self.workspace.history[path] = []
            self.workspace.history_indices[path] = -1

        pixmap = self.cv2_to_qpixmap(self.workspace.edited_images[path])
        self.current_image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.current_image_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.view.setFocus()

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
                box.text_color = QColor(b_data.get('text_color', "black"))
                box.stroke_width = b_data.get('stroke_width', 0)
                box.stroke_color = QColor(b_data.get('stroke_color', "white"))
                box.generated_mask = b_data.get('generated_mask', None)

                self.scene.addItem(box)
                
                if box.generated_mask is not None:
                    box.set_mask_display(box.generated_mask)

                if b_data.get('is_typeset', False):
                    box.toggle_typeset(force_state=True)

        if path not in self.workspace.history or not self.workspace.history[path]:
            self.commit_history("Initial State")
        else:
            self._refresh_history_ui()

        self.update_window_title()
        self.update_button_states()

        if not self.workspace.is_page_processed(path) and self.toolbar.chk_auto_process.isChecked() and self.yolo_model:
            QTimer.singleShot(100, self.run_auto_detect)

    def get_current_boxes_state(self):
        return [{
            'rect': item.rect(), 'pos': item.scenePos(), 'is_auto': getattr(item, 'is_auto', False),
            'raw_text': getattr(item, 'raw_text', ''), 'translated_text': getattr(item, 'translated_text', ''),
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
            'is_strikeout': getattr(item, 'is_strikeout', False),
            'text_color': getattr(item, 'text_color', QColor("black")).name(),
            'stroke_width': getattr(item, 'stroke_width', 0),
            'stroke_color': getattr(item, 'stroke_color', QColor("white")).name(),
            'generated_mask': getattr(item, 'generated_mask').copy() if getattr(item, 'generated_mask', None) is not None else None
        } for item in self.scene.items() if isinstance(item, BoundingBoxItem)]

    def save_current_page_state(self):
        if not self.workspace.current_image_path: return
        boxes = self.get_current_boxes_state()
        self.workspace.save_page_state(self.workspace.current_image_path, boxes)

    def commit_history(self, desc, aggregate=False):
        path = self.workspace.current_image_path
        if not path: return

        img = self.workspace.edited_images[path].copy()
        boxes = self.get_current_boxes_state()

        if path not in self.workspace.history:
            self.workspace.history[path] = []
            self.workspace.history_indices[path] = -1

        # If we are not at the end of the history stack, truncate the future steps before appending
        curr_idx = self.workspace.history_indices[path]
        if curr_idx < len(self.workspace.history[path]) - 1:
            self.workspace.history[path] = self.workspace.history[path][:curr_idx + 1]

        # Aggregate continuous changes of the same type into a single history step
        if aggregate and curr_idx >= 0:
            if self.workspace.history[path][curr_idx]['desc'] == desc:
                self.workspace.history[path][curr_idx]['boxes'] = boxes
                self.workspace.history[path][curr_idx]['image'] = img
                self._refresh_history_ui()
                self.update_button_states()
                return

        self.workspace.history[path].append({
            'desc': desc,
            'image': img,
            'boxes': boxes
        })

        self.workspace.history_indices[path] = len(self.workspace.history[path]) - 1

        self._refresh_history_ui()
        self.update_button_states()

    def _refresh_history_ui(self):
        path = self.workspace.current_image_path
        self.history_dock.history_list.blockSignals(True)
        self.history_dock.history_list.clear()
        if path and path in self.workspace.history:
            curr_idx = self.workspace.history_indices.get(path, -1)
            for idx, step in enumerate(self.workspace.history[path]):
                self.history_dock.history_list.addItem(f"{idx + 1}. {step['desc']}")

                # Visually indicate future states (redo-able steps)
                if idx > curr_idx:
                    item = self.history_dock.history_list.item(idx)
                    item.setForeground(Qt.gray)
                    f = item.font()
                    f.setItalic(True)
                    item.setFont(f)

            if curr_idx >= 0:
                self.history_dock.history_list.setCurrentRow(curr_idx)
        self.history_dock.history_list.blockSignals(False)

    def on_history_item_clicked(self, item):
        idx = self.history_dock.history_list.row(item)
        self.load_history_step(idx)

    def load_history_step(self, index):
        path = self.workspace.current_image_path
        if not path or path not in self.workspace.history: return
        history_list = self.workspace.history[path]
        if index < 0 or index >= len(history_list): return

        self.set_processing_lock(True)
        step = history_list[index]
        self.workspace.edited_images[path] = step['image'].copy()

        # Update current index (Do NOT truncate history yet)
        self.workspace.history_indices[path] = index

        # Redraw Image
        self.scene.clear()
        pixmap = self.cv2_to_qpixmap(self.workspace.edited_images[path])
        self.current_image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.current_image_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        # Redraw Boxes
        for b_data in step['boxes']:
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
            box.text_color = QColor(b_data.get('text_color', "black"))
            box.stroke_width = b_data.get('stroke_width', 0)
            box.stroke_color = QColor(b_data.get('stroke_color', "white"))
            box.generated_mask = b_data.get('generated_mask', None)

            self.scene.addItem(box)
            
            if box.generated_mask is not None:
                box.set_mask_display(box.generated_mask)
                
            if b_data.get('is_typeset', False):
                box.toggle_typeset(force_state=True)

        self._refresh_history_ui()
        self.set_processing_lock(False)
        self.update_button_states()

    def jump_to_image(self, target_idx):
        if not self.is_processing and self.workspace.has_images:
            if 0 <= target_idx < self.workspace.total_pages and target_idx != self.workspace.current_img_index:
                self.save_current_page_state()
                self.workspace.current_img_index = target_idx
                self.render_current_page()
            else:
                # Reset display to current page if they typed an out-of-bounds number
                self.nav.update_labels(self.workspace.current_page_number, self.workspace.total_pages)

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

            self.typeset_toolbar.combo_text_color.blockSignals(True)
            t_color_name = self.current_selected_box.text_color.name()
            for i in range(self.typeset_toolbar.combo_text_color.count()):
                if self.typeset_toolbar.combo_text_color.itemText(i).lower() == self.current_selected_box.text_color.name().lower() or \
                   QColor(self.typeset_toolbar.combo_text_color.itemText(i).lower()).name() == t_color_name:
                    self.typeset_toolbar.combo_text_color.setCurrentIndex(i)
                    break
            self.typeset_toolbar.combo_text_color.blockSignals(False)

            self.typeset_toolbar.spin_stroke_width.blockSignals(True)
            self.typeset_toolbar.spin_stroke_width.setValue(self.current_selected_box.stroke_width)
            self.typeset_toolbar.spin_stroke_width.blockSignals(False)
            
            self.typeset_toolbar.combo_stroke_color.blockSignals(True)
            color_name = self.current_selected_box.stroke_color.name()
            # Match the color dynamically, preventing case-sensitivity issues
            for i in range(self.typeset_toolbar.combo_stroke_color.count()):
                if self.typeset_toolbar.combo_stroke_color.itemText(i).lower() == self.current_selected_box.stroke_color.name().lower() or \
                   QColor(self.typeset_toolbar.combo_stroke_color.itemText(i).lower()).name() == color_name:
                    self.typeset_toolbar.combo_stroke_color.setCurrentIndex(i)
                    break
            self.typeset_toolbar.combo_stroke_color.blockSignals(False)

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
        self.commit_history("Add Box (Manual)")

    def delete_selected_box(self):
        count = 0
        for item in self.scene.selectedItems():
            if isinstance(item, BoundingBoxItem):
                self.scene.removeItem(item)
                count += 1
        if count > 0:
            self.commit_history(f"Delete {count} Box(es)")

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
