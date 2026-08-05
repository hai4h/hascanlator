from PySide6.QtWidgets import QKeySequenceEdit
from PySide6.QtCore import Qt

class AdaptiveKeySequenceEdit(QKeySequenceEdit):
    def __init__(self, key_sequence, parent=None):
        super().__init__(key_sequence, parent)
        self.setMaximumSequenceLength(1)

    def keyPressEvent(self, event):
        key = event.key()
        # Don't clear if the user is just pressing/holding down a modifier key
        if key not in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_unknown):
            # Block signals temporarily so it doesn't trigger a blank save before the new key registers
            self.blockSignals(True)
            self.clear()
            self.blockSignals(False)
        super().keyPressEvent(event)