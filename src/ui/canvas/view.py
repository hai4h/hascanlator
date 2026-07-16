from PySide6.QtWidgets import QGraphicsView
from PySide6.QtGui import QPainter
from PySide6.QtCore import Qt, Signal
from src.ui.canvas.items import BoundingBoxItem

class MangaCanvasView(QGraphicsView):
    resized = Signal() # Added signal to broadcast size changes

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._is_panning = False

    def resizeEvent(self, event):
        """Emit a signal when the canvas resizes so overlays can snap to edges."""
        super().resizeEvent(event)
        self.resized.emit()

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0: self.scale(1.15, 1.15)
            else: self.scale(1/1.15, 1/1.15)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start_x = event.position().x()
            self._pan_start_y = event.position().y()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            dx = event.position().x() - self._pan_start_x
            dy = event.position().y() - self._pan_start_y
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - dx)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - dy)
            self._pan_start_x = event.position().x()
            self._pan_start_y = event.position().y()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
            if event.button() == Qt.MiddleButton:
                self._is_panning = False
                self.setCursor(Qt.ArrowCursor)
                event.accept()
            else:
                super().mouseReleaseEvent(event)
