import cv2
import numpy as np
from PySide6.QtGui import QPixmap, QImage, QColor
from PySide6.QtCore import Qt, QRectF

from src.ui.canvas.items import BoundingBoxItem

class ImageOperationsMixin:
    #  OPENCV IMAGE HELPERS
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

    #  PEEK AND UNDO LOGIC
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

    def smart_clean_bubble(self, boxes=None, commit=True):
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

            # 3. Smart Masking Pipeline
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

            # Heuristic check: Is this a standard white bubble?
            # We check the perimeter pixels of the bounding box. If mostly white, it's a bubble.
            top, bottom = gray[0, :], gray[-1, :]
            left, right = gray[:, 0], gray[:, -1]
            border_pixels = np.concatenate([top, bottom, left, right])
            white_ratio = np.sum(border_pixels > 200) / max(1, len(border_pixels))

            is_standard_bubble = white_ratio > 0.65
            clean_mask = np.zeros_like(gray)

            if is_standard_bubble:
                #  CLASSICAL METHOD (White Bubbles)
                # Extremely accurate for standard black text on white backgrounds.
                _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for contour in contours:
                    cx, cy, cw, ch = cv2.boundingRect(contour)
                    margin = 3
                    touches_edge = (cx <= margin) or (cy <= margin) or (cx + cw >= w - margin) or (cy + ch >= h - margin)
                    area = cv2.contourArea(contour)
                    too_huge = area > (w * h * 0.5)

                    if not touches_edge and not too_huge:
                        cv2.drawContours(clean_mask, [contour], -1, 255, thickness=cv2.FILLED)

                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
                clean_mask = cv2.dilate(clean_mask, kernel, iterations=2)
            else:
                # COMPLEX BACKGROUND METHOD (Screentones / Dark Arts)                 # Uses Morphological Gradient to find high-frequency edges (detects both black and white text natively)
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
                _, binary = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                # Clean up noise and form solid text stroke masks
                clean_mask = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
                # Dilate slightly more (iterations=2) to guarantee no anti-aliased text pixels leak into the inpaint
                clean_mask = cv2.dilate(clean_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=2)

            # 4. Modual Inpainting Execution (Prepared for Future AI Model)
            # Future AI Hook: if self.settings.value("use_ai_inpaint"): cleaned_roi = self._run_ai_inpaint(roi, clean_mask)
            # Classic Fallback:
            if is_standard_bubble:
                cleaned_roi = cv2.inpaint(roi, clean_mask, 7, cv2.INPAINT_TELEA)
            else:
                # Navier-Stokes (NS) blends fluid backgrounds/gradients slightly better than Telea
                cleaned_roi = cv2.inpaint(roi, clean_mask, 7, cv2.INPAINT_NS)

            img[y:y+h, x:x+w] = cleaned_roi

            # Store flag inside the box so the auto-expander knows whether to expand or not
            box._is_standard_bubble = is_standard_bubble

        # 5. Auto-Expand Bounding Boxes to fill the clean bubble
        gray_clean = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Milder median blur: destroys screentone dots but keeps thin bubble walls intact (11 was too destructive)
        blurred = cv2.medianBlur(gray_clean, 5)
        max_h, max_w = gray_clean.shape

        for box in target_boxes:
            rect = box.sceneBoundingRect()
            bx, by, bw, bh = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())

            curr_x1, curr_y1 = max(0, bx), max(0, by)
            curr_x2, curr_y2 = min(max_w, bx + bw), min(max_h, by + bh)

            # Unify Auto-Expansion: Dynamically sample the cleaned background to find the wall threshold
            center_roi = blurred[curr_y1:curr_y2, curr_x1:curr_x2]
            base_gray = np.median(center_roi) if center_roi.size > 0 else 255

            if base_gray < 50:
                # Dark bubble, walls are likely white/bright
                wall_thresh = min(255, base_gray + 50)
                _, obstacle_map = cv2.threshold(blurred, wall_thresh, 255, cv2.THRESH_BINARY)
            else:
                # White/Gray/Screentone bubble, walls are likely black/dark
                wall_thresh = max(0, base_gray - 50)
                _, obstacle_map = cv2.threshold(blurred, wall_thresh, 255, cv2.THRESH_BINARY_INV)

            # Strict tolerance to ensure it stops exactly at thin lines
            tolerance = 0.02

            can_exp_left = can_exp_right = can_exp_top = can_exp_bottom = True
            step = 1 # 1 pixel step prevents jumping over 1-pixel thin borders
            max_dim = max(bw, bh) * 2 # Prevent infinite expansion if the bubble is open

            while can_exp_left or can_exp_right or can_exp_top or can_exp_bottom:
                # Ignore the corners of the bounding box to allow deeper expansion into oval bubbles
                # Reduced back to 15% to prevent the collision-check line from becoming too small and slipping through gaps
                y_margin = int((curr_y2 - curr_y1) * 0.15)
                chk_y1 = curr_y1 + y_margin
                chk_y2 = curr_y2 - y_margin
                if chk_y2 <= chk_y1: chk_y1, chk_y2 = curr_y1, curr_y2

                x_margin = int((curr_x2 - curr_x1) * 0.15)
                chk_x1 = curr_x1 + x_margin
                chk_x2 = curr_x2 - x_margin
                if chk_x2 <= chk_x1: chk_x1, chk_x2 = curr_x1, curr_x2

                if can_exp_left:
                    nx = max(0, curr_x1 - step)
                    if nx == curr_x1 or (curr_x2 - nx) > max_dim:
                        can_exp_left = False
                    else:
                        edge = obstacle_map[chk_y1:chk_y2, nx:curr_x1]
                        if np.sum(edge > 0) / max(1, edge.size) > tolerance:
                            can_exp_left = False
                        else:
                            curr_x1 = nx

                if can_exp_right:
                    nx = min(max_w, curr_x2 + step)
                    if nx == curr_x2 or (nx - curr_x1) > max_dim:
                        can_exp_right = False
                    else:
                        edge = obstacle_map[chk_y1:chk_y2, curr_x2:nx]
                        if np.sum(edge > 0) / max(1, edge.size) > tolerance:
                            can_exp_right = False
                        else:
                            curr_x2 = nx

                if can_exp_top:
                    ny = max(0, curr_y1 - step)
                    if ny == curr_y1 or (curr_y2 - ny) > max_dim:
                        can_exp_top = False
                    else:
                        edge = obstacle_map[ny:curr_y1, chk_x1:chk_x2]
                        if np.sum(edge > 0) / max(1, edge.size) > tolerance:
                            can_exp_top = False
                        else:
                            curr_y1 = ny

                if can_exp_bottom:
                    ny = min(max_h, curr_y2 + step)
                    if ny == curr_y2 or (ny - curr_y1) > max_dim:
                        can_exp_bottom = False
                    else:
                        edge = obstacle_map[curr_y2:ny, chk_x1:chk_x2]
                        if np.sum(edge > 0) / max(1, edge.size) > tolerance:
                            can_exp_bottom = False
                        else:
                            curr_y2 = ny

            # Add padding so Typeset Text doesn't touch the bubble walls
            pad = 4
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

        if commit:
            self.commit_history(f"Smart Clean ({len(target_boxes)} Boxes)")

    #  TYPESETTING CONTROLS
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

    def set_text_stroke_width(self, width):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.stroke_width = max(0, width)
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Stroke Width")

    def set_text_stroke_color(self, color_name):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                from PySide6.QtGui import QColor
                box.stroke_color = QColor(color_name.lower())
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Stroke Color")

    def set_text_color(self, color_name):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                from PySide6.QtGui import QColor
                box.text_color = QColor(color_name.lower())
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Text Color")

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

        align_val = self.settings.value("default_align", "center")
        if align_val == "left": box.align = Qt.AlignLeft
        elif align_val == "right": box.align = Qt.AlignRight
        else: box.align = Qt.AlignCenter

        try:
            box.indent = int(self.settings.value("default_indent", 5))
        except ValueError:
            box.indent = 5

        box.text_color = QColor(self.settings.value("default_text_color", "black").lower())
        box.stroke_width = int(self.settings.value("default_stroke_width", 0))
        box.stroke_color = QColor(self.settings.value("default_stroke_color", "white").lower())

    def reset_text_font(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                self.apply_default_font_settings(box)
                if box.is_typeset:
                    box.update_typeset()
                changed = True
        if changed: self.commit_history("Reset Font")
