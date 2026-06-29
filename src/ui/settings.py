from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget, QLabel, QPushButton, QTabWidget

class SettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Settings & Model Manager")
        self.resize(500, 400)
        
        self.main_window.model_status_changed.connect(self.update_ui_state)
        
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        models_tab = QWidget()
        models_layout = QVBoxLayout(models_tab)
        
        models_layout.addWidget(QLabel("<b>MangaOCR (Text Recognition)</b><br>Reads Japanese text inside the boxes."))
        self.mocr_status_label = QLabel()
        self.btn_load_mocr = QPushButton("Download / Load Model")
        self.btn_load_mocr.clicked.connect(lambda: self.main_window.load_model("manga_ocr"))
        models_layout.addWidget(self.mocr_status_label)
        models_layout.addWidget(self.btn_load_mocr)
        
        models_layout.addWidget(QLabel("<hr>"))
        
        models_layout.addWidget(QLabel("<b>YOLOv8 Bubble Detector</b><br>Machine learning-based accurate speech bubble locator."))
        self.yolo_status_label = QLabel()
        self.btn_load_yolo = QPushButton("Download / Load Model")
        self.btn_load_yolo.clicked.connect(lambda: self.main_window.load_model("yolo_detector"))
        models_layout.addWidget(self.yolo_status_label)
        models_layout.addWidget(self.btn_load_yolo)
        
        models_layout.addStretch()
        tabs.addTab(models_tab, "Models")
        layout.addWidget(tabs)
        self.update_ui_state() 

    def update_ui_state(self):
        if self.main_window.mocr_model is not None:
            self.mocr_status_label.setText("Status: <font color='green'>Loaded in Memory / Ready</font>")
            self.btn_load_mocr.setEnabled(False)
        elif self.main_window.mocr_is_loading:
            self.mocr_status_label.setText("Status: <font color='orange'>Downloading / Loading... (Check terminal)</font>")
            self.btn_load_mocr.setEnabled(False)
        else:
            self.mocr_status_label.setText("Status: <font color='red'>Not Loaded</font>")
            self.btn_load_mocr.setEnabled(True)

        if self.main_window.yolo_model is not None:
            self.yolo_status_label.setText("Status: <font color='green'>Loaded in Memory / Ready</font>")
            self.btn_load_yolo.setEnabled(False)
        elif self.main_window.yolo_is_loading:
            self.yolo_status_label.setText("Status: <font color='orange'>Downloading / Loading... (Check terminal)</font>")
            self.btn_load_yolo.setEnabled(False)
        else:
            self.yolo_status_label.setText("Status: <font color='red'>Not Loaded</font>")
            self.btn_load_yolo.setEnabled(True)