import cv2
import numpy as np
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt

from src.ui.canvas.items import BoundingBoxItem

class ImageOperationsMixin:
    # --- OPENCV IMAGE HELPERS ---
    def imread_utf8(self, filepath):
        """Allows cv2 to load files that contain non-ascii characters in their folder path."""
        img_array = np.fromfile(filepath, np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    def cv2_to_qpixmap(self, cv_img):
        """Converts an OpenCV BGR numpy array to QPixmap for rendering."""
        h, w, ch = cv_img.shape
        bytes_per_line = ch * w
        converted = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        qimg = QImage(converted.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)

    # --- PEEK AND UNDO LOGIC ---
    def show_original_image(self):
        path = self.workspace.current_image_path
        if path and path in self.workspace.original_images:
            self.current_image_item.setPixmap(self.cv2_to_qpixmap(self.workspace.original_images[path]))
            for item in self.scene.items():
                if isinstance(item, BoundingBoxItem):
                    item.setVisible(False)

    def show_edited_image(self):
        path = self.workspace.current_image_path
        if path and path in self.workspace.edited_images:
            self.current_image_item.setPixmap(self.cv2_to_qpixmap(self.workspace.edited_images[path]))
            for item in self.scene.items():
                if isinstance(item, BoundingBoxItem):
                    item.setVisible(True)

    def undo_edit(self):
        path = self.workspace.current_image_path
        if path and path in self.workspace.history_indices:
            idx = self.workspace.history_indices[path] - 1
            if idx >= 0:
                self.load_history_step(idx)

    def redo_edit(self):
        path = self.workspace.current_image_path
        if path and path in self.workspace.history_indices:
            idx = self.workspace.history_indices[path] + 1
            if idx < len(self.workspace.history.get(path, [])):
                self.load_history_step(idx)

    def smart_clean_bubble(self, boxes=None):
        # UI signals occasionally pass `checked` (bool) as the first argument, handle it safely
        if isinstance(boxes, bool) or boxes is None:
            target_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        else:
            target_boxes = boxes

        if not self.workspace.current_image_path or not target_boxes:
            return

        path = self.workspace.current_image_path

        img = self.workspace.edited_images[path].copy()

        for box in target_boxes:
            rect = box.sceneBoundingRect()
            x, y, w, h = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())

            # 2. Boundary Safety Check
            x, y = max(0, x), max(0, y)
            w, h = min(img.shape[1] - x, w), min(img.shape[0] - y, h)
            if w <= 0 or h <= 0: continue

            roi = img[y:y+h, x:x+w]

            # 3. Smart Masking
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            clean_mask = np.zeros_like(gray)

            for contour in contours:
                cx, cy, cw, ch = cv2.boundingRect(contour)
                margin = 3
                touches_edge = (cx <= margin) or (cy <= margin) or (cx + cw >= w - margin) or (cy + ch >= h - margin)
                area = cv2.contourArea(contour)
                too_huge = area > (w * h * 0.5)

                if not touches_edge and not too_huge:
                    cv2.drawContours(clean_mask, [contour], -1, 255, thickness=cv2.FILLED)

            # 4. Aggressive Mask Expansion
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            clean_mask = cv2.dilate(clean_mask, kernel, iterations=2)

            # 5. Erase text
            cleaned_roi = cv2.inpaint(roi, clean_mask, 7, cv2.INPAINT_TELEA)
            img[y:y+h, x:x+w] = cleaned_roi

        # 6. Auto-Expand Bounding Boxes to fill the clean bubble
        gray_clean = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Threshold: 220 to 255 is considered "white space" inside the bubble
        _, thresh = cv2.threshold(gray_clean, 220, 255, cv2.THRESH_BINARY)
        max_h, max_w = thresh.shape

        from PySide6.QtCore import QRectF

        for box in target_boxes:
            rect = box.sceneBoundingRect()
            bx, by, bw, bh = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())

            curr_x1, curr_y1 = max(0, bx), max(0, by)
            curr_x2, curr_y2 = min(max_w, bx + bw), min(max_h, by + bh)

            can_exp_left = can_exp_right = can_exp_top = can_exp_bottom = True
            step = 2
            max_dim = max(bw, bh) * 3
            tolerance = 0.02 # Allow 2% noise (handles slight screentones/artifacts)

            while can_exp_left or can_exp_right or can_exp_top or can_exp_bottom:
                if can_exp_left:
                    nx = max(0, curr_x1 - step)
                    if nx == curr_x1 or (curr_x2 - nx) > max_dim:
                        can_exp_left = False
                    else:
                        edge = thresh[curr_y1:curr_y2, nx:curr_x1]
                        if np.sum(edge == 0) / max(1, edge.size) > tolerance:
                            can_exp_left = False
                        else:
                            curr_x1 = nx

                if can_exp_right:
                    nx = min(max_w, curr_x2 + step)
                    if nx == curr_x2 or (nx - curr_x1) > max_dim:
                        can_exp_right = False
                    else:
                        edge = thresh[curr_y1:curr_y2, curr_x2:nx]
                        if np.sum(edge == 0) / max(1, edge.size) > tolerance:
                            can_exp_right = False
                        else:
                            curr_x2 = nx

                if can_exp_top:
                    ny = max(0, curr_y1 - step)
                    if ny == curr_y1 or (curr_y2 - ny) > max_dim:
                        can_exp_top = False
                    else:
                        edge = thresh[ny:curr_y1, curr_x1:curr_x2]
                        if np.sum(edge == 0) / max(1, edge.size) > tolerance:
                            can_exp_top = False
                        else:
                            curr_y1 = ny

                if can_exp_bottom:
                    ny = min(max_h, curr_y2 + step)
                    if ny == curr_y2 or (ny - curr_y1) > max_dim:
                        can_exp_bottom = False
                    else:
                        edge = thresh[curr_y2:ny, curr_x1:curr_x2]
                        if np.sum(edge == 0) / max(1, edge.size) > tolerance:
                            can_exp_bottom = False
                        else:
                            curr_y2 = ny

            # Add padding so Typeset Text doesn't touch the bubble walls
            pad = 6
            final_x1, final_y1 = curr_x1 + pad, curr_y1 + pad
            final_x2, final_y2 = curr_x2 - pad, curr_y2 - pad

            # Failsafe: Ensure it didn't collapse on itself
            if final_x2 <= final_x1: final_x1, final_x2 = curr_x1, curr_x2
            if final_y2 <= final_y1: final_y1, final_y2 = curr_y1, curr_y2

            box.setRect(QRectF(final_x1, final_y1, final_x2 - final_x1, final_y2 - final_y1))
            if box.is_typeset:
                box.update_typeset()

        # 7. Save and Render
        self.workspace.edited_images[path] = img
        self.show_edited_image()
        self.update_button_states()
        self.commit_history(f"Smart Clean ({len(target_boxes)} Boxes)")

    # --- TYPESETTING CONTROLS ---
    def toggle_typeset_view(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.toggle_typeset()
                changed = True
        if changed: self.commit_history("Toggle Typeset")

    def set_text_alignment(self, align):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.align = align
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Set Text Alignment")

    def set_text_indent(self, delta):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.indent = max(0, box.indent + delta)
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Indent")

    def set_text_valignment(self, valign):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.valign = valign
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Set Vertical Alignment")

    def set_text_line_spacing(self, delta):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.line_spacing = max(0.5, round(box.line_spacing + delta, 1))
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Line Spacing")

    def reset_text_alignment(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.align = Qt.AlignCenter
                box.valign = Qt.AlignVCenter
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Reset Alignment")

    def reset_text_spacing(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.indent = 5
                box.line_spacing = 1.0
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Reset Spacing")

    def set_text_font_family(self, family):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.font_family = family
                if box.is_typeset: box.update_typeset()
                changed = True

        # Maintain list of recent fonts
        if hasattr(self, 'recent_fonts'):
            if family in self.recent_fonts:
                self.recent_fonts.remove(family)
            self.recent_fonts.insert(0, family)
            if len(self.recent_fonts) > 5:
                self.recent_fonts = self.recent_fonts[:5]

        self.refresh_font_combo(current_font=family)
        if changed: self.commit_history("Change Font Family")

    def set_text_font_size_exact(self, size):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.font_size = max(1, size)
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Font Size")

    def toggle_text_bold(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_bold = not box.is_bold
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Bold")

    def toggle_text_italic(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_italic = not box.is_italic
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Italic")

    def toggle_text_underline(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_underline = not box.is_underline
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Underline")

    def toggle_text_strikeout(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_strikeout = not box.is_strikeout
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Strikeout")

    def apply_default_font_settings(self, box):
        """Applies global font settings from QSettings to a specific box."""
        box.font_family = self.settings.value("default_font_family", "sans-serif")
        box.font_size = int(self.settings.value("default_font_size", 16))

        # Determine boolean value safely from QSettings strings ("true"/"false")
        def _get_bool(key, default=False):
            val = self.settings.value(key, default)
            if isinstance(val, str):
                return val.lower() == "true"
            return bool(val)

        box.is_bold = _get_bool("default_font_bold")
        box.is_italic = _get_bool("default_font_italic")
        box.is_underline = _get_bool("default_font_underline")
        box.is_strikeout = _get_bool("default_font_strikeout")

    def reset_text_font(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                self.apply_default_font_settings(box)
                if box.is_typeset:
                    box.update_typeset()
                changed = True
        if changed: self.commit_history("Reset Font")
