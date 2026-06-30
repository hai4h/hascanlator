from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel

class EditorDockWidget(QDockWidget):
    """The right-side panel for editing raw text and translation."""
    def __init__(self, parent=None):
        super().__init__("Editor", parent)
        self._setup_ui()

    def _setup_ui(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.ocr_input = QTextEdit()
        self.ocr_input.setStyleSheet("font-size: 16px;")
        self.trans_input = QTextEdit()
        
        tools_layout = QHBoxLayout()
        
        self.btn_run_ocr = QPushButton("Run OCR")
        self.btn_translate_box = QPushButton("Translate Box")
        self.btn_delete_box = QPushButton("Delete Box")
        self.btn_translate_all = QPushButton("Translate All Boxes")
        
        tools_layout.addWidget(self.btn_run_ocr)
        tools_layout.addWidget(self.btn_translate_box)
        tools_layout.addWidget(self.btn_delete_box)

        self.btn_run_ocr.setEnabled(False)
        self.btn_translate_box.setEnabled(False)
        self.btn_translate_all.setEnabled(False)
        self.btn_delete_box.setEnabled(False)
        self.ocr_input.setEnabled(False)
        self.trans_input.setEnabled(False)
        
        layout.addLayout(tools_layout)
        layout.addWidget(self.btn_translate_all)
        layout.addWidget(QLabel("Raw Text (OCR):"))
        layout.addWidget(self.ocr_input)
        layout.addWidget(QLabel("Translation:"))
        layout.addWidget(self.trans_input)

        self.setWidget(panel)