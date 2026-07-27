from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QListWidget
from PySide6.QtCore import Qt

class HistoryDockWidget(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Changes", parent)

        self.setMinimumWidth(150)

        self._setup_ui()

    def _setup_ui(self):
        self.history_list = QListWidget()
        self.history_list.setAlternatingRowColors(True)
        self.history_list.setStyleSheet("QListWidget::item { padding: 6px 4px; border-bottom: 1px solid #3c3c3c; }")

        # Enable word wrapping and dynamic resizing
        self.history_list.setWordWrap(True)
        self.history_list.setTextElideMode(Qt.ElideNone)
        self.history_list.setResizeMode(QListWidget.Adjust)

        self.setWidget(self.history_list)

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
        self.ocr_input.setReadOnly(True)
        self.trans_input = QTextEdit()

        tools_layout = QHBoxLayout()
        self.btn_run_ocr = QPushButton("Run OCR")
        self.btn_translate_box = QPushButton("Translate")
        self.btn_delete_box = QPushButton("Delete Box")

        self.btn_trans_type_sel = QPushButton("Translate && Typeset Selected")
        self.btn_trans_type_all = QPushButton("Translate && Typeset All Boxes")

        tools_layout.addWidget(self.btn_run_ocr)
        tools_layout.addWidget(self.btn_translate_box)
        tools_layout.addWidget(self.btn_delete_box)

        self.btn_run_ocr.setEnabled(False)
        self.btn_translate_box.setEnabled(False)
        self.btn_trans_type_sel.setEnabled(False)
        self.btn_trans_type_all.setEnabled(False)
        self.btn_delete_box.setEnabled(False)
        self.ocr_input.setEnabled(False)
        self.trans_input.setEnabled(False)

        layout.addLayout(tools_layout)
        layout.addWidget(self.btn_trans_type_sel)
        layout.addWidget(self.btn_trans_type_all)
        layout.addWidget(QLabel("Original (OCR):"))
        layout.addWidget(self.ocr_input)
        layout.addWidget(QLabel("Translation:"))
        layout.addWidget(self.trans_input)

        self.setWidget(panel)
