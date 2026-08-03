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

    def generate_bubble_mask(self, boxes=None, auto_inpaint=False, commit=True):
        if isinstance(boxes, bool) or boxes is None:
            target_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        else:
            target_boxes = boxes

        if not self.workspace.current_image_path or not target_boxes:
            return

        if not self.masking_model:
            if not self.ensure_models_ready([("masking_model", "local_masking")]): return

        self._pending_mask_boxes = target_boxes
        self._pending_auto_inpaint = auto_inpaint
        self._pending_mask_commit = commit

        path = self.workspace.current_image_path
        img = self.workspace.edited_images[path].copy()

        self.set_processing_lock(True)
        self.update_window_title("Generating Text Mask...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.statusBar().showMessage("Running masking model on full page...")

        from src.core.detection import MaskingWorker
        self.mask_worker = MaskingWorker(self.masking_model, img)
        self.mask_worker.process_finished.connect(self.on_mask_generated)
        self.mask_worker.error.connect(self.on_mask_error)
        self.mask_worker.start()

    def on_mask_generated(self, full_mask):
        import cv2
        target_boxes = getattr(self, '_pending_mask_boxes', [])

        path = self.workspace.current_image_path
        if not path or path not in self.workspace.edited_images:
            self._cleanup_masking_state()
            return

        img = self.workspace.edited_images[path]

        for box in target_boxes:
            rect = box.rect()
            scene_tl = box.mapToScene(rect.topLeft())
            scene_br = box.mapToScene(rect.bottomRight())

            x, y = int(scene_tl.x()), int(scene_tl.y())
            w, h = int(scene_br.x() - scene_tl.x()), int(scene_br.y() - scene_tl.y())

            x, y = max(0, x), max(0, y)
            w, h = min(img.shape[1] - x, w), min(img.shape[0] - y, h)
            if w <= 0 or h <= 0: continue

            raw_mask_roi = full_mask[y:y+h, x:x+w].copy()

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask_roi = cv2.dilate(raw_mask_roi, kernel, iterations=3)

            box.generated_mask = mask_roi
            box.set_mask_display(mask_roi)

            # --- CLASSIFY BUBBLE VS FLOATING TEXT ---
            orig_img = self.workspace.original_images[path]
            roi_img = orig_img[y:y+h, x:x+w]

            if roi_img.size > 0:
                gray_roi = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)

                # Expand the text mask by 4 pixels to guarantee we completely cover the Japanese text and its anti-aliasing
                kernel_bg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
                text_mask = cv2.dilate(raw_mask_roi, kernel_bg)
                bg_mask = cv2.bitwise_not(text_mask)

                bg_pixels = gray_roi[bg_mask > 127]

                is_bubble = True
                bg_is_noisy = False

                if len(bg_pixels) > 0:
                    bg_mean = np.mean(bg_pixels)
                    bg_std = np.std(bg_pixels)

                    # 1. Edge Detection (Detects drawing lines, panel borders, picture frames)
                    edges = cv2.Canny(gray_roi, 50, 150)
                    bg_edges = edges[bg_mask > 127]

                    # If even 1% of the background consists of strong edges/lines, it is drawn art.
                    edge_ratio = np.sum(bg_edges > 0) / len(bg_pixels)

                    # 2. Strict Uniformity Checks
                    white_ratio = np.sum(bg_pixels > 230) / len(bg_pixels)
                    black_ratio = np.sum(bg_pixels < 25) / len(bg_pixels)

                    text_lightness = box.text_color.lightness()
                    contrast = abs(bg_mean - text_lightness)

                    # --- BACKGROUND TYPE CLASSIFICATION ---
                    # Noisy if it has art lines, high variance (screentones), or low contrast
                    if edge_ratio > 0.01 or bg_std > 20 or contrast < 80:
                        bg_is_noisy = True
                    else:
                        bg_is_noisy = False

                    # --- SPEECH BUBBLE CLASSIFICATION ---
                    # Very pure white or black region (This will be used for auto-expand logic later)
                    if white_ratio > 0.85 or black_ratio > 0.85:
                        is_bubble = True
                    else:
                        is_bubble = False

                box.is_bubble = is_bubble
                box.bg_is_noisy = bg_is_noisy

                # Auto-apply a contrasting stroke if the background is noisy art
                if bg_is_noisy and box.stroke_width == 0:
                    box.stroke_width = int(self.settings.value("auto_stroke_size", 4))
                    from PySide6.QtGui import QColor
                    if box.text_color.lightness() < 128:
                        box.stroke_color = QColor("white")
                    else:
                        box.stroke_color = QColor("black")

        auto_inpaint = getattr(self, '_pending_auto_inpaint', False)
        commit = getattr(self, '_pending_mask_commit', True)

        self._cleanup_masking_state()
        self.update_button_states()

        if auto_inpaint:
            commit_state = getattr(self, '_pending_inpaint_commit', True)
            self.inpaint_bubble_mask(boxes=target_boxes, commit=commit_state)
        else:
            if commit:
                self.commit_history(f"Generate Mask ({len(target_boxes)} Boxes)")
            if getattr(self, '_is_auto_scan_pipeline', False):
                self._execute_pipeline_post_inpaint()

    def _cleanup_masking_state(self):
        self._pending_mask_boxes = []
        self._pending_auto_inpaint = False
        self._pending_mask_commit = False
        self.progress_bar.setVisible(False)
        self.set_processing_lock(False)
        self.update_window_title()
        self.statusBar().showMessage("Ready")

    def on_mask_error(self, err_msg):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Masking Error", str(err_msg))
        self._cleanup_masking_state()

    def inpaint_bubble_mask(self, boxes=None, commit=True):
        if isinstance(boxes, bool) or boxes is None:
            target_boxes = [item for item in self.scene.selectedItems() if isinstance(item, BoundingBoxItem)]
        else:
            target_boxes = boxes

        if not self.workspace.current_image_path or not target_boxes:
            return

        boxes_needing_mask = [b for b in target_boxes if getattr(b, 'generated_mask', None) is None]
        if boxes_needing_mask:
            self._pending_inpaint_commit = commit
            self.generate_bubble_mask(boxes=target_boxes, auto_inpaint=True, commit=False)
            return

        if not self.inpaint_model:
            if not self.ensure_models_ready([("inpaint_model", "local_inpaint")]): return

        path = self.workspace.current_image_path
        img = self.workspace.edited_images[path].copy()

        boxes_data = []
        for box in target_boxes:
            mask = getattr(box, 'generated_mask', None)
            if mask is None: continue

            rect = box.rect()
            scene_tl = box.mapToScene(rect.topLeft())
            scene_br = box.mapToScene(rect.bottomRight())

            x, y = int(scene_tl.x()), int(scene_tl.y())
            w, h = int(scene_br.x() - scene_tl.x()), int(scene_br.y() - scene_tl.y())

            x, y = max(0, x), max(0, y)
            w, h = min(img.shape[1] - x, w), min(img.shape[0] - y, h)
            if w <= 0 or h <= 0: continue

            boxes_data.append((x, y, w, h, mask))

        if not boxes_data:
            return

        self._pending_inpaint_commit = commit
        self._pending_inpaint_boxes = target_boxes

        self.set_processing_lock(True)
        self.update_window_title("Inpainting...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"Inpainting {len(boxes_data)} regions...")

        from src.core.detection import InpaintingWorker
        self.inpaint_worker = InpaintingWorker(self.inpaint_model, img, boxes_data)
        self.inpaint_worker.progress_percent.connect(self.progress_bar.setValue)
        self.inpaint_worker.process_finished.connect(self.on_inpaint_finished)
        self.inpaint_worker.error.connect(self.on_inpaint_error)
        self.inpaint_worker.start()

    def on_inpaint_finished(self, res_img):
        path = self.workspace.current_image_path
        if not path:
            self._cleanup_inpaint_state()
            return

        self.workspace.edited_images[path] = res_img

        target_boxes = getattr(self, '_pending_inpaint_boxes', [])
        for box in target_boxes:
            box.clear_mask_display()

        self.show_edited_image()

        commit = getattr(self, '_pending_inpaint_commit', True)
        if commit:
            self.commit_history(f"Inpaint ({len(target_boxes)} Boxes)")

        self._cleanup_inpaint_state()

        if getattr(self, '_is_auto_scan_pipeline', False):
            self._execute_pipeline_post_inpaint()

    def _cleanup_inpaint_state(self):
        self._pending_inpaint_boxes = []
        self._pending_inpaint_commit = False
        self.progress_bar.setVisible(False)
        self.set_processing_lock(False)
        self.update_window_title()
        self.statusBar().showMessage("Ready")

    def on_inpaint_error(self, err_msg):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Inpaint Error", str(err_msg))
        self._cleanup_inpaint_state()

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
        if changed: self.commit_history("Set Text Alignment", aggregate=True)

    def set_text_indent(self, delta):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.indent = max(0, box.indent + delta)
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Indent", aggregate=True)

    def set_text_valignment(self, valign):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.valign = valign
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Set Vertical Alignment", aggregate=True)

    def set_text_line_spacing(self, delta):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.line_spacing = max(0.5, round(box.line_spacing + delta, 1))
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Line Spacing", aggregate=True)

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
        if changed: self.commit_history("Change Stroke Width", aggregate=True)

    def set_text_stroke_color(self, color_name):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                from PySide6.QtGui import QColor
                box.stroke_color = QColor(color_name.lower())
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Stroke Color", aggregate=True)

    def set_text_color(self, color_name):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                from PySide6.QtGui import QColor
                box.text_color = QColor(color_name.lower())
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Text Color", aggregate=True)

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
        if changed: self.commit_history("Change Font Family", aggregate=True)

    def set_text_font_size_exact(self, size):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.font_size = max(1, size)
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Change Font Size", aggregate=True)

    def toggle_text_bold(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_bold = not box.is_bold
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Bold", aggregate=True)

    def toggle_text_italic(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_italic = not box.is_italic
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Italic", aggregate=True)

    def toggle_text_underline(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_underline = not box.is_underline
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Underline", aggregate=True)

    def toggle_text_strikeout(self):
        changed = False
        for box in self.scene.selectedItems():
            if isinstance(box, BoundingBoxItem):
                box.is_strikeout = not box.is_strikeout
                if box.is_typeset: box.update_typeset()
                changed = True
        if changed: self.commit_history("Toggle Strikeout", aggregate=True)

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
