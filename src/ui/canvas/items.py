from PySide6.QtWidgets import QGraphicsPolygonItem, QMenu, QGraphicsPixmapItem
from PySide6.QtGui import QPen, QColor, QFont, QPainterPath, QTextOption, QPolygonF, QTextLayout, QFontMetrics, QPainter, QImage, QPixmap
from PySide6.QtCore import Qt, QPointF, QRectF
import cv2
import numpy as np

class BoundingBoxItem(QGraphicsPolygonItem):
    NONE, LEFT, TOP, RIGHT, BOTTOM, TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT = range(-9, 0)

    def __init__(self, rect_or_poly, is_auto=False, shape_type=None, parent=None):
        if isinstance(rect_or_poly, QRectF):
            self._rect = rect_or_poly
            poly = QPolygonF(rect_or_poly)
            self.shape_type = "rect" if shape_type is None else shape_type
        else:
            poly = rect_or_poly
            self._rect = poly.boundingRect()
            if shape_type is None:
                self.shape_type = "rect" if poly.count() == 4 else "polygon"
            else:
                self.shape_type = shape_type

        super().__init__(poly, parent)
        self.setFlags(QGraphicsPolygonItem.ItemIsSelectable | QGraphicsPolygonItem.ItemIsMovable | QGraphicsPolygonItem.ItemSendsGeometryChanges)
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
        self.text_layout = None
        self.auto_fit_target_ratio = 0.8
        self.is_typeset = False
        self.stroke_pixmap = None
        self.stroke_offset = QPointF(0, 0)
        self.is_bubble = True
        self.bg_is_noisy = False
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

        self.text_color = QColor("black")
        self.stroke_width = 0
        self.stroke_color = QColor("white")

        self.generated_mask = None

    def rect(self):
        """Backwards compatibility for methods expecting a rect."""
        return self._rect if self.shape_type == "rect" else self.polygon().boundingRect()

    def boundingRect(self):
        margin = float(self.handle_size)
        if self.shape_type == "rect":
            return self._rect.adjusted(-margin, -margin, margin, margin)
        else:
            return self.polygon().boundingRect().adjusted(-margin, -margin, margin, margin)

    def shape(self):
        path = QPainterPath()
        if self.shape_type == "rect":
            path.addRect(self.boundingRect())
        else:
            path.addPolygon(self.polygon())
            s = self.handle_size
            poly = self.polygon()
            for i in range(poly.count()):
                pt = poly[i]
                path.addRect(pt.x() - s, pt.y() - s, s * 2, s * 2)
        return path

    def set_mask_display(self, mask_array):
        h, w = mask_array.shape[:2]

        # Ensure mask is 8-bit single channel
        if mask_array.dtype != np.uint8:
            mask_array = mask_array.astype(np.uint8)

        rgba = np.zeros((h, w, 4), dtype=np.uint8)

        # Draw red contours mapping the detected bounding edge
        contours, _ = cv2.findContours(mask_array, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(rgba, contours, -1, (255, 0, 0, 255), 2)

        # Apply semi-transparent red inside the bounds
        rgba[mask_array > 127] = (255, 0, 0, 100)

        bytes_per_line = 4 * w
        qimg = QImage(rgba.data, w, h, bytes_per_line, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)

        if not hasattr(self, 'mask_item'):
            self.mask_item = QGraphicsPixmapItem(self)
            self.mask_item.setZValue(-0.5) # Float between bounding box and background

        self.mask_item.setPixmap(pixmap)
        self.mask_item.setPos(self.rect().topLeft())
        self.mask_item.show()

    def clear_mask_display(self):
        if hasattr(self, 'mask_item'):
            self.mask_item.hide()
            self.mask_item.setPixmap(QPixmap())
        self.generated_mask = None

    def update_typeset(self):
        if not self.is_typeset or not self.translated_text.strip():
            self.text_layout = None
            self.update()
            return

        font = QFont(self.font_family)
        font.setPixelSize(self.font_size)
        font.setBold(self.is_bold)
        font.setItalic(self.is_italic)
        font.setUnderline(self.is_underline)
        font.setStrikeOut(self.is_strikeout)

        self.text_layout = self._create_layout_for_polygon(self.translated_text, self.polygon(), font)

        if self.stroke_width > 0 and self.is_typeset and self.translated_text.strip():
            import cv2
            import numpy as np
            from PySide6.QtGui import QImage, QPainter, QPixmap

            pad = self.stroke_width + 4
            rect = self.polygon().boundingRect()

            # Find the true rendered bounds including any overflowing words
            min_x, max_x = rect.left(), rect.right()
            min_y, max_y = rect.top(), rect.bottom()

            if self.text_layout:
                for i in range(self.text_layout.lineCount()):
                    line = self.text_layout.lineAt(i)
                    nw = line.naturalTextWidth()
                    w = line.width()
                    px = line.position().x()
                    py = line.position().y()

                    if self.align == Qt.AlignCenter or self.align == Qt.AlignHCenter:
                        overflow = max(0, nw - w)
                        lx = px - overflow / 2.0
                        rx = px + w + overflow / 2.0
                    elif self.align == Qt.AlignRight:
                        overflow = max(0, nw - w)
                        lx = px - overflow
                        rx = px + w
                    else: # Left align
                        lx = px
                        rx = px + max(nw, w)

                    min_x = min(min_x, lx)
                    max_x = max(max_x, rx)
                    min_y = min(min_y, py)
                    max_y = max(max_y, py + line.height())

            tw, th = max(1, int(max_x - min_x) + 2), max(1, int(max_y - min_y) + 2)

            qimg = QImage(tw + pad*2, th + pad*2, QImage.Format_RGBA8888)
            qimg.fill(Qt.transparent)

            painter = QPainter(qimg)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            painter.setRenderHint(QPainter.Antialiasing, True)

            # Offset the painter so the text layout draws perfectly inside our padded QImage
            painter.translate(-min_x + pad, -min_y + pad)
            painter.setPen(QPen(Qt.black))
            self.text_layout.draw(painter, QPointF(0, 0))
            painter.end()

            # Extract alpha channel
            arr = np.frombuffer(qimg.bits(), dtype=np.uint8).reshape((th + pad*2, tw + pad*2, 4)).copy()
            alpha = arr[:, :, 3]

            # Dilate the alpha to create a smooth, rounded stroke
            k_size = self.stroke_width * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
            dilated_alpha = cv2.dilate(alpha, kernel)

            # Light anti-aliasing on the hard edge
            dilated_alpha = cv2.GaussianBlur(dilated_alpha, (3, 3), 0)

            stroke_rgba = np.zeros((th + pad*2, tw + pad*2, 4), dtype=np.uint8)
            r_c, g_c, b_c, _ = self.stroke_color.getRgb()
            stroke_rgba[:, :, 0] = r_c
            stroke_rgba[:, :, 1] = g_c
            stroke_rgba[:, :, 2] = b_c
            stroke_rgba[:, :, 3] = dilated_alpha

            out_qimg = QImage(stroke_rgba.data, tw + pad*2, th + pad*2, (tw + pad*2)*4, QImage.Format_RGBA8888)
            self.stroke_pixmap = QPixmap.fromImage(out_qimg.copy())
            self.stroke_offset = QPointF(min_x - pad, min_y - pad)
        else:
            self.stroke_pixmap = None

        self.update()

    def _create_layout_for_polygon(self, text, polygon, font):
        layout = QTextLayout(text, font)

        option = QTextOption()
        option.setWrapMode(QTextOption.WordWrap)
        option.setAlignment(self.align)
        layout.setTextOption(option)

        layout.beginLayout()

        font_metrics = QFontMetrics(font)
        line_height = int(font_metrics.height() * self.line_spacing)

        current_y = polygon.boundingRect().top() + self.indent

        while True:
            line = layout.createLine()
            if not line.isValid():
                break

            min_x, max_x = self.get_polygon_x_bounds_at_y(polygon, current_y, current_y + line_height)

            if min_x is None:
                available_width = 0
            else:
                available_width = (max_x - min_x) - (self.indent * 2)

            if available_width <= 0:
                available_width = 10

            line.setLineWidth(available_width)

            if min_x is not None:
                line.setPosition(QPointF(min_x + self.indent, current_y))
            else:
                line.setPosition(QPointF(polygon.boundingRect().left() + self.indent, current_y))

            current_y += line_height

        layout.endLayout()

        # Apply vertical alignment offset
        if layout.lineCount() > 0:
            last_line = layout.lineAt(layout.lineCount() - 1)
            total_text_height = last_line.position().y() + line_height - (polygon.boundingRect().top() + self.indent)

            poly_h = polygon.boundingRect().height() - (self.indent * 2)

            if self.valign == Qt.AlignVCenter:
                y_offset = (poly_h - total_text_height) / 2.0
            elif self.valign == Qt.AlignBottom:
                y_offset = poly_h - total_text_height
            else:
                y_offset = 0

            if y_offset != 0:
                for i in range(layout.lineCount()):
                    line = layout.lineAt(i)
                    line.setPosition(line.position() + QPointF(0, y_offset))

        return layout

    def get_polygon_x_bounds_at_y(self, polygon, y, next_y):
        bounds = polygon.boundingRect()
        slice_rect = QRectF(bounds.left() - 100, y, bounds.width() + 200, next_y - y)

        poly_path = QPainterPath()
        poly_path.addPolygon(polygon)

        slice_path = QPainterPath()
        slice_path.addRect(slice_rect)

        intersection = poly_path.intersected(slice_path)
        if intersection.isEmpty():
            return None, None

        int_bounds = intersection.boundingRect()
        return int_bounds.left(), int_bounds.right()

    def auto_fit_font_size(self):
        if not self.translated_text.strip(): return

        best_size = 8
        low = 8
        high = 100

        font = QFont(self.font_family)
        font.setBold(self.is_bold)
        font.setItalic(self.is_italic)
        font.setUnderline(self.is_underline)
        font.setStrikeOut(self.is_strikeout)

        poly_height = self.polygon().boundingRect().height() - (self.indent * 2)
        target_height = poly_height * self.auto_fit_target_ratio

        while low <= high:
            mid = (low + high) // 2
            font.setPixelSize(mid)
            layout = self._create_layout_for_polygon(self.translated_text, self.polygon(), font)

            total_height = 0
            has_overflow = False

            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                # WordWrap allows words to spill over the set width if they cannot be broken.
                # We add a 2.0 pixel tolerance to avoid false positives from trailing spaces or anti-aliasing.
                if line.naturalTextWidth() > line.width() + 2.0:
                    has_overflow = True
                    break

            if layout.lineCount() > 0:
                last_line = layout.lineAt(layout.lineCount() - 1)
                total_height = last_line.position().y() + int(QFontMetrics(font).height() * self.line_spacing) - self.polygon().boundingRect().top() - self.indent

            if not has_overflow and total_height <= target_height:
                best_size = mid
                low = mid + 1
            else:
                high = mid - 1

        self.font_size = best_size
        self.update_typeset()

    def set_vertex_count(self, n):
        import math
        bounds = self.rect()
        cx = bounds.center().x()
        cy = bounds.center().y()
        rx = bounds.width() / 2.0
        ry = bounds.height() / 2.0

        new_poly = QPolygonF()
        if n == 4:
            self.shape_type = "rect"
            self._rect = bounds
            new_poly.append(QPointF(bounds.left(), bounds.top()))
            new_poly.append(QPointF(bounds.right(), bounds.top()))
            new_poly.append(QPointF(bounds.right(), bounds.bottom()))
            new_poly.append(QPointF(bounds.left(), bounds.bottom()))
        else:
            self.shape_type = "polygon"
            # Start at 0 radians (right-most point) to ensure pointed left/right corners
            # and flat edges at the top/bottom (ideal for horizontal text wrapping)
            offset = 0
            for i in range(n):
                angle = offset + (i * 2 * math.pi / n)
                px = cx + rx * math.cos(angle)
                py = cy + ry * math.sin(angle)
                new_poly.append(QPointF(px, py))

        self.setPolygon(new_poly)
        if self.is_typeset:
            self.update_typeset()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)

        if self.is_typeset and self.text_layout:
            painter.save()

            if self.stroke_width > 0 and getattr(self, 'stroke_pixmap', None) is not None:
                painter.drawPixmap(self.stroke_offset, self.stroke_pixmap)

            painter.setPen(QPen(self.text_color))
            self.text_layout.draw(painter, QPointF(0, 0))
            painter.restore()

        # Draw handles for the user to manipulate
        if self.isSelected() and not self.is_typeset:
            painter.save()
            painter.setBrush(Qt.white)
            painter.setPen(QPen(Qt.black, 1))
            s = 8
            if self.shape_type == "polygon":
                poly = self.polygon()
                for i in range(poly.count()):
                    pt = poly[i]
                    painter.drawRect(QRectF(pt.x() - s/2, pt.y() - s/2, s, s))
            else:
                r = self._rect
                centers = [
                    r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight(),
                    QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()),
                    QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom())
                ]
                for pt in centers:
                    painter.drawRect(QRectF(pt.x() - s/2, pt.y() - s/2, s, s))
            painter.restore()

    def toggle_typeset(self, force_state=None):
        self.is_typeset = force_state if force_state is not None else not self.is_typeset

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
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsPolygonItem.ItemSelectedHasChanged:
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
        if self.shape_type == "polygon":
            poly = self.polygon()
            for i in range(poly.count()):
                pt = poly[i]
                if abs(pt.x() - pos.x()) <= self.handle_size and abs(pt.y() - pos.y()) <= self.handle_size:
                    return i
            return self.NONE

        r = self._rect
        x, y = pos.x(), pos.y()
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
        if self.current_handle == self.NONE:
            self.setCursor(Qt.SizeAllCursor if self.isSelected() else Qt.ArrowCursor)
        elif self.current_handle >= 0:
            self.setCursor(Qt.CrossCursor)
        else:
            if self.current_handle in (self.TOP_LEFT, self.BOTTOM_RIGHT): self.setCursor(Qt.SizeFDiagCursor)
            elif self.current_handle in (self.TOP_RIGHT, self.BOTTOM_LEFT): self.setCursor(Qt.SizeBDiagCursor)
            elif self.current_handle in (self.LEFT, self.RIGHT): self.setCursor(Qt.SizeHorCursor)
            elif self.current_handle in (self.TOP, self.BOTTOM): self.setCursor(Qt.SizeVerCursor)
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
            self.prepareGeometryChange()
            if self.resizing_handle >= 0:
                poly = self.polygon()
                poly[self.resizing_handle] = event.pos()
                self.setPolygon(poly)
            else:
                rect, pos, min_size = QRectF(self._rect), event.pos(), 15
                if self.resizing_handle in (self.LEFT, self.TOP_LEFT, self.BOTTOM_LEFT): rect.setLeft(min(pos.x(), rect.right() - min_size))
                if self.resizing_handle in (self.RIGHT, self.TOP_RIGHT, self.BOTTOM_RIGHT): rect.setRight(max(pos.x(), rect.left() + min_size))
                if self.resizing_handle in (self.TOP, self.TOP_LEFT, self.TOP_RIGHT): rect.setTop(min(pos.y(), rect.bottom() - min_size))
                if self.resizing_handle in (self.BOTTOM, self.BOTTOM_LEFT, self.BOTTOM_RIGHT): rect.setBottom(max(pos.y(), rect.top() + min_size))
                self._rect = rect
                self.setPolygon(QPolygonF(self._rect))

            if self.is_typeset:
                self.update_typeset()
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.resizing_handle != self.NONE:
            self.resizing_handle = self.NONE
            event.accept()
        else: super().mouseReleaseEvent(event)
