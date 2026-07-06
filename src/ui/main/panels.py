from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
from PySide6.QtCore import Qt

class EditorDockWidget(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Editor", parent)
        self._setup_ui()

    def _setup_ui(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Basic Translation Tools
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

        # Typesetting Sub-Panel
        ts_layout = QVBoxLayout()
        ts_layout.addWidget(QLabel("<hr><b>Typesetting & Cleaning</b>"))
        
        align_layout = QHBoxLayout()
        self.btn_align_left = QPushButton("Left")
        self.btn_align_center = QPushButton("Center")
        self.btn_align_right = QPushButton("Right")
        align_layout.addWidget(self.btn_align_left)
        align_layout.addWidget(self.btn_align_center)
        align_layout.addWidget(self.btn_align_right)
        ts_layout.addLayout(align_layout)

        indent_layout = QHBoxLayout()
        self.btn_indent_minus = QPushButton("- Indent")
        self.btn_indent_plus = QPushButton("+ Indent")
        indent_layout.addWidget(self.btn_indent_minus)
        indent_layout.addWidget(self.btn_indent_plus)
        ts_layout.addLayout(indent_layout)
        
        self.btn_clean_bubble = QPushButton("Smart Clean Bubble")
        self.btn_toggle_typeset = QPushButton("Toggle Typeset Visibility")
        
        ts_layout.addWidget(self.btn_clean_bubble)
        ts_layout.addWidget(self.btn_toggle_typeset)
        
        self.btn_align_left.setEnabled(False)
        self.btn_align_center.setEnabled(False)
        self.btn_align_right.setEnabled(False)
        self.btn_indent_minus.setEnabled(False)
        self.btn_indent_plus.setEnabled(False)
        self.btn_clean_bubble.setEnabled(False)
        self.btn_toggle_typeset.setEnabled(False)
        
        layout.addLayout(ts_layout)

        self.setWidget(panel)