from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget
from PySide6.QtCore import Qt

from src.ui.settings.models import ModelsTab
from src.ui.settings.translation import TranslationTab
from src.ui.settings.fonts import FontsTab
from src.ui.settings.keybinds import KeybindsTab

class SettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Settings & Model Manager")

        screen_geom = self.screen().availableGeometry()
        self.resize(int(screen_geom.width() * 0.5), int(screen_geom.height() * 0.65))
        self.setMinimumSize(800, 600)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.main_window.model_status_changed.connect(self.update_ui_state)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.tab_models = ModelsTab(main_window)
        self.tab_translation = TranslationTab(main_window)
        self.tab_fonts = FontsTab(main_window)
        self.tab_keybinds = KeybindsTab(main_window)

        self.tabs.addTab(self.tab_models, "Models")
        self.tabs.addTab(self.tab_translation, "Translation")
        self.tabs.addTab(self.tab_fonts, "Fonts")
        self.tabs.addTab(self.tab_keybinds, "Keybinds")

        layout.addWidget(self.tabs)

        self.update_ui_state()

    def update_ui_state(self):
        try:
            self.tab_models.update_ui_state()
            self.tab_translation.update_ui_state()
        except RuntimeError:
            pass # Dialog might be closing