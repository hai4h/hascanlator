from dataclasses import dataclass

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor


@dataclass
class BoxState:
    rect: QRectF
    pos: QPointF
    is_auto: bool = False
    raw_text: str = ""
    translated_text: str = ""
    is_typeset: bool = False
    is_bubble: bool = True
    bg_is_noisy: bool = False
    bg_is_solid: bool = False
    align: Qt.AlignmentFlag = Qt.AlignCenter
    valign: Qt.AlignmentFlag = Qt.AlignVCenter
    indent: int = 5
    line_spacing: float = 1.0
    font_family: str = "sans-serif"
    font_size: int = 16
    is_bold: bool = False
    is_italic: bool = False
    is_underline: bool = False
    is_strikeout: bool = False
    text_color: str = "black"
    stroke_width: int = 0
    stroke_color: str = "white"
    generated_mask: np.ndarray | None = None
    auto_fit_target_ratio: float = 0.8

    def __getstate__(self):
        """Convert PySide6 objects and numpy arrays to primitives before pickling to disk."""
        state = self.__dict__.copy()

        # 1. Convert QRectF to (x, y, w, h) tuple
        if state.get("rect") is not None:
            r = state["rect"]
            state["rect"] = (r.x(), r.y(), r.width(), r.height())

        # 2. Convert QPointF to (x, y) tuple
        if state.get("pos") is not None:
            state["pos"] = (state["pos"].x(), state["pos"].y())

        # 3. Convert Qt.AlignmentFlag to int
        if state.get("align") is not None:
            state["align"] = int(state["align"])
        if state.get("valign") is not None:
            state["valign"] = int(state["valign"])

        # 4. Only encode mask to PNG when pickling to disk
        if state.get("generated_mask") is not None:
            _, buf = cv2.imencode(".png", state["generated_mask"])
            state["generated_mask"] = buf.tobytes()

        return state

    def __setstate__(self, state):
        """Rebuild PySide6 objects and numpy arrays when loading from disk."""
        # 1. Rebuild QRectF (with fallback for legacy pickles that stored a polygon)
        rect_data = state.get("rect")
        if rect_data is None and state.get("polygon") is not None:
            rect_data = state.pop("polygon")
        if rect_data is not None:
            if len(rect_data) == 4 and not isinstance(rect_data[0], (tuple, list)):
                state["rect"] = QRectF(*rect_data)
            else:
                # Legacy polygon point list: derive its bounding rect
                x_coords = [p[0] for p in rect_data]
                y_coords = [p[1] for p in rect_data]
                state["rect"] = QRectF(
                    min(x_coords),
                    min(y_coords),
                    max(x_coords) - min(x_coords),
                    max(y_coords) - min(y_coords),
                )

        # 2. Rebuild QPointF
        if state.get("pos") is not None:
            state["pos"] = QPointF(state["pos"][0], state["pos"][1])

        # 3. Rebuild Qt.AlignmentFlag
        if state.get("align") is not None:
            state["align"] = Qt.AlignmentFlag(state["align"])
        if state.get("valign") is not None:
            state["valign"] = Qt.AlignmentFlag(state["valign"])

        # 4. Decode mask from PNG bytes back to numpy array
        if state.get("generated_mask") is not None:
            arr = np.frombuffer(state["generated_mask"], dtype=np.uint8)
            state["generated_mask"] = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)

        self.__dict__.update(state)

    @classmethod
    def from_item(cls, item: BoundingBoxItem) -> BoxState:
        return cls(
            rect=item.rect(),
            pos=item.scenePos(),
            is_auto=item.is_auto,
            raw_text=item.raw_text,
            translated_text=item.translated_text,
            is_typeset=item.is_typeset,
            is_bubble=item.is_bubble,
            bg_is_noisy=item.bg_is_noisy,
            bg_is_solid=getattr(item, "bg_is_solid", False),
            align=item.align,
            valign=item.valign,
            indent=item.indent,
            line_spacing=item.line_spacing,
            font_family=item.font_family,
            font_size=item.font_size,
            is_bold=item.is_bold,
            is_italic=item.is_italic,
            is_underline=item.is_underline,
            is_strikeout=item.is_strikeout,
            text_color=item.text_color.name(),
            stroke_color=item.stroke_color.name(),
            stroke_width=item.stroke_width,
            generated_mask=item.generated_mask,  # Store raw numpy array in RAM!
            auto_fit_target_ratio=item.auto_fit_target_ratio,
        )

    def apply_to(self, item: BoundingBoxItem):
        item.setPos(self.pos)
        item.raw_text = self.raw_text
        item.translated_text = self.translated_text
        item.is_bubble = self.is_bubble
        item.bg_is_noisy = self.bg_is_noisy
        item.bg_is_solid = self.bg_is_solid
        item.align = self.align
        item.valign = self.valign
        item.indent = self.indent
        item.line_spacing = self.line_spacing
        item.font_family = self.font_family
        item.font_size = self.font_size
        item.is_bold = self.is_bold
        item.is_italic = self.is_italic
        item.is_underline = self.is_underline
        item.is_strikeout = self.is_strikeout
        item.text_color = QColor(self.text_color)
        item.stroke_color = QColor(self.stroke_color)
        item.stroke_width = self.stroke_width
        item.auto_fit_target_ratio = self.auto_fit_target_ratio

        # generated_mask is always a numpy array in RAM now
        mask = self.generated_mask
        item.generated_mask = mask
        if mask is not None:
            item.set_mask_display(mask)

        if self.is_typeset:
            item.toggle_typeset(force_state=True)
