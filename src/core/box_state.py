from dataclasses import dataclass, field
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPolygonF
import cv2
import numpy as np

@dataclass
class BoxState:
    polygon: QPolygonF
    pos: QPointF
    shape_type: str = "rect"
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
    generated_mask: bytes | None = None  # Stored as compressed PNG bytes
    auto_fit_target_ratio: float = 0.8

    @staticmethod
    def encode_mask(mask_array: np.ndarray) -> bytes | None:
        if mask_array is None: return None
        _, buf = cv2.imencode('.png', mask_array)
        return buf.tobytes()

    @staticmethod
    def decode_mask(mask_data: bytes) -> np.ndarray | None:
        if mask_data is None: return None
        arr = np.frombuffer(mask_data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)

    @classmethod
    def from_item(cls, item: "BoundingBoxItem") -> "BoxState":
        return cls(
            polygon=item.polygon(),
            pos=item.scenePos(),
            shape_type=item.shape_type,
            is_auto=item.is_auto,
            raw_text=item.raw_text,
            translated_text=item.translated_text,
            is_typeset=item.is_typeset,
            is_bubble=item.is_bubble,
            bg_is_noisy=item.bg_is_noisy,
            bg_is_solid=getattr(item, 'bg_is_solid', False),
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
            generated_mask=cls.encode_mask(item.generated_mask),
            auto_fit_target_ratio=item.auto_fit_target_ratio
        )

    def apply_to(self, item: "BoundingBoxItem"):
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

        mask = self.decode_mask(self.generated_mask)
        item.generated_mask = mask
        if mask is not None:
            item.set_mask_display(mask)

        if self.is_typeset:
            item.toggle_typeset(force_state=True)
