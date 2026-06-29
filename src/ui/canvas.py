from PySide6.QtWidgets import QGraphicsView, QGraphicsRectItem
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPen, QColor, QPainter

class MangaCanvasView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._is_panning = False

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0: self.scale(1.15, 1.15)
            else: self.scale(1/1.15, 1/1.15)
        else: super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start_x = event.position().x()
            self._pan_start_y = event.position().y()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            dx = event.position().x() - self._pan_start_x
            dy = event.position().y() - self._pan_start_y
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - dx)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - dy)
            self._pan_start_x = event.position().x()
            self._pan_start_y = event.position().y()
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else: super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.scene().selectedItems():
                if isinstance(item, BoundingBoxItem):
                    self.scene().removeItem(item)
        else: super().keyPressEvent(event)

class BoundingBoxItem(QGraphicsRectItem):
    NONE, LEFT, TOP, RIGHT, BOTTOM, TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT = range(9)

    def __init__(self, rect, is_auto=False, parent=None):
        super().__init__(rect, parent)
        self.setFlags(QGraphicsRectItem.ItemIsSelectable | QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True) 
        self.is_auto = is_auto 
        
        pen = QPen(QColor(0, 255, 0))
        pen.setWidth(2)
        pen.setCosmetic(True) 
        self.setPen(pen)
        self.brush_selected = QColor(0, 255, 0, 40)
        self.brush_normal = QColor(0, 0, 0, 0)
        self.setBrush(self.brush_normal)
        self.handle_size = 8 
        self.current_handle = self.NONE
        self.resizing_handle = self.NONE
        
        self.raw_text = ""
        self.translated_text = ""

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemSelectedHasChanged:
            self.setBrush(self.brush_selected if self.isSelected() else self.brush_normal)
            pen = QPen(QColor(255, 100, 100) if self.isSelected() else QColor(0, 255, 0), 2)
            pen.setCosmetic(True)
            self.setPen(pen)
        return super().itemChange(change, value)

    def get_handle_at(self, pos):
        r, x, y = self.rect(), pos.x(), pos.y()
        l = abs(x - r.left()) <= self.handle_size
        rt = abs(x - r.right()) <= self.handle_size
        t = abs(y - r.top()) <= self.handle_size
        b = abs(y - r.bottom()) <= self.handle_size
        
        if t and l: return self.TOP_LEFT
        if t and rt: return self.TOP_RIGHT
        if b and l: return self.BOTTOM_LEFT
        if b and rt: return self.BOTTOM_RIGHT
        if t: return self.TOP
        if b: return self.BOTTOM
        if l: return self.LEFT
        if rt: return self.RIGHT
        return self.NONE

    def hoverMoveEvent(self, event):
        if not self.isSelected():
            self.setCursor(Qt.ArrowCursor)
            return super().hoverMoveEvent(event)
        self.current_handle = self.get_handle_at(event.pos())
        if self.current_handle in (self.TOP_LEFT, self.BOTTOM_RIGHT): self.setCursor(Qt.SizeFDiagCursor)
        elif self.current_handle in (self.TOP_RIGHT, self.BOTTOM_LEFT): self.setCursor(Qt.SizeBDiagCursor)
        elif self.current_handle in (self.LEFT, self.RIGHT): self.setCursor(Qt.SizeHorCursor)
        elif self.current_handle in (self.TOP, self.BOTTOM): self.setCursor(Qt.SizeVerCursor)
        else: self.setCursor(Qt.SizeAllCursor if self.isSelected() else Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        self.current_handle = self.NONE
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if self.current_handle != self.NONE and self.isSelected():
            self.resizing_handle = self.current_handle
            event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resizing_handle != self.NONE:
            rect = self.rect()
            pos = event.pos()
            min_size = 15 
            if self.resizing_handle in (self.LEFT, self.TOP_LEFT, self.BOTTOM_LEFT): rect.setLeft(min(pos.x(), rect.right() - min_size))
            if self.resizing_handle in (self.RIGHT, self.TOP_RIGHT, self.BOTTOM_RIGHT): rect.setRight(max(pos.x(), rect.left() + min_size))
            if self.resizing_handle in (self.TOP, self.TOP_LEFT, self.TOP_RIGHT): rect.setTop(min(pos.y(), rect.bottom() - min_size))
            if self.resizing_handle in (self.BOTTOM, self.BOTTOM_LEFT, self.BOTTOM_RIGHT): rect.setBottom(max(pos.y(), rect.top() + min_size))
            self.setRect(rect)
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.resizing_handle != self.NONE:
            self.resizing_handle = self.NONE
            event.accept()
        else: super().mouseReleaseEvent(event)