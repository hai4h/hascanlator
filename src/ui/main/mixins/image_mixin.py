import cv2
import numpy as np
from PySide6.QtGui import QPixmap, QImage

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

    def show_edited_image(self):
        path = self.workspace.current_image_path
        if path and path in self.workspace.edited_images:
            self.current_image_item.setPixmap(self.cv2_to_qpixmap(self.workspace.edited_images[path]))

    def undo_edit(self):
        path = self.workspace.current_image_path
        if path and self.workspace.undo_stacks.get(path):
            last_img = self.workspace.undo_stacks[path].pop()
            self.workspace.edited_images[path] = last_img
            self.show_edited_image()
            self.update_button_states()

    def smart_clean_bubble(self):
        if not self.workspace.current_image_path or not self.current_selected_box: return
        path = self.workspace.current_image_path
        
        # 1. Save Undo State
        current_img = self.workspace.edited_images[path].copy()
        self.workspace.undo_stacks[path].append(current_img)
        if len(self.workspace.undo_stacks[path]) > 5:
            self.workspace.undo_stacks[path].pop(0)
            
        rect = self.current_selected_box.sceneBoundingRect()
        x, y, w, h = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        
        img = self.workspace.edited_images[path]
        
        # 2. Boundary Safety Check
        x, y = max(0, x), max(0, y)
        w, h = min(img.shape[1] - x, w), min(img.shape[0] - y, h)
        if w <= 0 or h <= 0: return
        
        roi = img[y:y+h, x:x+w]
        
        # 3. Smart Masking
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # Use Otsu's thresholding to find the core black text
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        clean_mask = np.zeros_like(gray)
        
        for contour in contours:
            cx, cy, cw, ch = cv2.boundingRect(contour)
            
            # Filter 1: Edge touching (increased margin slightly to 3 for safety)
            margin = 3
            touches_edge = (cx <= margin) or (cy <= margin) or (cx + cw >= w - margin) or (cy + ch >= h - margin)
            
            # Filter 2: Too huge
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
        
        # 6. Save and Render
        self.workspace.edited_images[path] = img
        self.show_edited_image()
        self.update_button_states()

    # --- TYPESETTING CONTROLS ---
    def toggle_typeset_view(self):
        if not self.current_selected_box: return
        self.current_selected_box.toggle_typeset()
        
    def set_text_alignment(self, align):
        if not self.current_selected_box: return
        self.current_selected_box.align = align
        if self.current_selected_box.is_typeset:
            self.current_selected_box.update_typeset()

    def set_text_indent(self, delta):
        if not self.current_selected_box: return
        self.current_selected_box.indent = max(0, self.current_selected_box.indent + delta)
        if self.current_selected_box.is_typeset:
            self.current_selected_box.update_typeset()

    def set_text_valignment(self, valign):
        if not self.current_selected_box: return
        self.current_selected_box.valign = valign
        if self.current_selected_box.is_typeset:
            self.current_selected_box.update_typeset()