from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem
from PySide6.QtGui import QPen, QColor, QFont, QPainterPath, QTextOption
from PySide6.QtCore import Qt

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

        self.handle_size = 12
        self.current_handle = self.NONE
        self.resizing_handle = self.NONE

        self.raw_text = ""
        self.translated_text = ""

        # --- Typesetting Variables ---
        self.text_item = QGraphicsTextItem(self)
        self.text_item.hide()

        self.text_item.setAcceptedMouseButtons(Qt.NoButton)
        self.text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        self.text_item.setAcceptHoverEvents(False)
        self.text_item.setZValue(-1)

        # Enforce strict word wrapping (avoids breaking in the middle of words)
        text_option = self.text_item.document().defaultTextOption()
        text_option.setWrapMode(QTextOption.WordWrap)
        self.text_item.document().setDefaultTextOption(text_option)

        self.is_typeset = False
        self.align = Qt.AlignCenter
        self.valign = Qt.AlignVCenter
        self.indent = 5
        self.line_spacing = 1.0

        # Font Settings
        self.font_family = "sans-serif"
        self.font_size = 16
        self.is_bold = False
        self.is_italic = False
        self.is_underline = False
        self.is_strikeout = False

    def boundingRect(self):
        """Expand the invisible hit-box so we can grab the edges from the outside."""
        margin = float(self.handle_size)
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def shape(self):
        """Register the expanded hit-box for mouse hover events."""
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def update_typeset(self):
        r = self.rect()

        # Subtract indent from text width so Qt perfectly centers it physically
        usable_width = max(10.0, r.width() - (self.indent * 2))
        self.text_item.setTextWidth(usable_width)

        align_str = "center"
        if self.align == Qt.AlignLeft: align_str = "left"
        elif self.align == Qt.AlignRight: align_str = "right"

        weight = "bold" if self.is_bold else "normal"
        style = "italic" if self.is_italic else "normal"

        decorations = []
        if self.is_underline: decorations.append("underline")
        if self.is_strikeout: decorations.append("line-through")
        text_decor = " ".join(decorations) if decorations else "none"

        text = self.translated_text.replace('\n', '<br>')
        # Removed CSS margin, using precise coordinate positioning instead for perfect alignment
        html = f"<div align='{align_str}' style='line-height: {self.line_spacing}; color: black; font-family: \"{self.font_family}\", sans-serif; font-size: {self.font_size}px; font-weight: {weight}; font-style: {style}; text-decoration: {text_decor};'>{text}</div>"

        self.text_item.setHtml(html)

        text_h = self.text_item.boundingRect().height()
        box_h = r.height()

        if self.valign == Qt.AlignTop: y_pos = r.top() + self.indent
        elif self.valign == Qt.AlignBottom: y_pos = r.bottom() - text_h - self.indent
        else: y_pos = r.top() + (box_h - text_h) / 2.0

        self.text_item.setPos(r.left() + self.indent, y_pos)

    def toggle_typeset(self, force_state=None):
        self.is_typeset = force_state if force_state is not None else not self.is_typeset
        self.text_item.setVisible(self.is_typeset)

        if self.is_typeset:
            self.update_typeset()
            self.setBrush(QColor(255, 255, 255, 1))
            if self.isSelected():
                self.setPen(QPen(QColor(100, 100, 255), 1, Qt.DashLine))
            else:
                self.setPen(QPen(Qt.transparent))
        else:
            self.setBrush(self.brush_selected if self.isSelected() else self.brush_normal)
            pen = QPen(QColor(255, 100, 100) if self.isSelected() else QColor(0, 255, 0), 2)
            pen.setCosmetic(True)
            self.setPen(pen)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemSelectedHasChanged:
            if self.is_typeset:
                if self.isSelected():
                    self.setPen(QPen(QColor(100, 100, 255), 1, Qt.DashLine))
                else:
                    self.setPen(QPen(Qt.transparent))
                self.setBrush(QColor(255, 255, 255, 1))
            else:
                self.setBrush(self.brush_selected if self.isSelected() else self.brush_normal)
                pen = QPen(QColor(255, 100, 100) if self.isSelected() else QColor(0, 255, 0), 2)
                pen.setCosmetic(True)
                self.setPen(pen)
        return super().itemChange(change, value)

    def get_handle_at(self, pos):
        r = self.rect()
        x, y = pos.x(), pos.y()

        # Prevent handle overlap on tiny boxes by limiting the INSIDE grab area,
        # but keep the OUTSIDE grab area large (self.handle_size)
        in_x = min(self.handle_size, r.width() / 3.0)
        in_y = min(self.handle_size, r.height() / 3.0)
        out = self.handle_size

        l = (r.left() - out <= x <= r.left() + in_x)
        rt = (r.right() - in_x <= x <= r.right() + out)
        t = (r.top() - out <= y <= r.top() + in_y)
        b = (r.bottom() - in_y <= y <= r.bottom() + out)

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
            rect, pos, min_size = self.rect(), event.pos(), 15
            if self.resizing_handle in (self.LEFT, self.TOP_LEFT, self.BOTTOM_LEFT): rect.setLeft(min(pos.x(), rect.right() - min_size))
            if self.resizing_handle in (self.RIGHT, self.TOP_RIGHT, self.BOTTOM_RIGHT): rect.setRight(max(pos.x(), rect.left() + min_size))
            if self.resizing_handle in (self.TOP, self.TOP_LEFT, self.TOP_RIGHT): rect.setTop(min(pos.y(), rect.bottom() - min_size))
            if self.resizing_handle in (self.BOTTOM, self.BOTTOM_LEFT, self.BOTTOM_RIGHT): rect.setBottom(max(pos.y(), rect.top() + min_size))

            self.setRect(rect)
            if self.is_typeset:
                self.update_typeset()
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.resizing_handle != self.NONE:
            self.resizing_handle = self.NONE
            event.accept()
        else: super().mouseReleaseEvent(event)
