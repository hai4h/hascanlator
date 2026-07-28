from PySide6.QtCore import QThread, Signal, QRectF

class DetectionWorker(QThread):
    process_finished = Signal(list)
    error = Signal(str)

    def __init__(self, image_path, yolo_model):
        super().__init__()
        self.image_path = image_path
        self.yolo_model = yolo_model

    def run(self):
        try:
            if not self.yolo_model:
                raise RuntimeError("Model not loaded.")

            results = self.yolo_model.predict(self.image_path, conf=0.25, verbose=False)
            raw_boxes = []
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    pad = 5
                    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
                    w, h = (x2 - x1) + (pad * 2), (y2 - y1) + (pad * 2)
                    raw_boxes.append(QRectF(x1, y1, w, h))

            # Post-process: Merge overlapping or adjacent boxes (separated lines of the same bubble)
            merged_boxes = []

            # Manga text is vertical, meaning lines are separated horizontally (X-axis).
            # Lowered x_margin to avoid jumping across distinct bubbles.
            x_margin = 12
            y_margin = 0

            for box in raw_boxes:
                matched_clusters = []
                expanded_box = box.adjusted(-x_margin, -y_margin, x_margin, y_margin)

                for idx, cluster in enumerate(merged_boxes):
                    if expanded_box.intersects(cluster):
                        # Ultra-Strict Heuristic: Lines in the same bubble are highly aligned vertically.
                        # Require at least 60% vertical overlap to fuse them. This prevents diagonal/staggered
                        # bubbles from merging just because their corners touch.
                        overlap_top = max(box.top(), cluster.top())
                        overlap_bottom = min(box.bottom(), cluster.bottom())
                        overlap_height = max(0, overlap_bottom - overlap_top)

                        min_height = min(box.height(), cluster.height())

                        if (overlap_height / max(1.0, min_height)) > 0.60:
                            matched_clusters.append(idx)

                if not matched_clusters:
                    merged_boxes.append(box)
                else:
                    first_idx = matched_clusters[0]
                    merged_boxes[first_idx] = merged_boxes[first_idx].united(box)
                    # If the new box bridges multiple existing clusters, merge them all into the first one
                    for idx in reversed(matched_clusters[1:]):
                        merged_boxes[first_idx] = merged_boxes[first_idx].united(merged_boxes[idx])
                        del merged_boxes[idx]

            self.process_finished.emit(merged_boxes)
        except Exception as e:
            self.error.emit(str(e))


class MaskingWorker(QThread):
    process_finished = Signal(object)
    error = Signal(str)

    def __init__(self, masking_model, img):
        super().__init__()
        self.masking_model = masking_model
        self.img = img

    def run(self):
        try:
            import cv2
            import numpy as np

            img_rgb = cv2.cvtColor(self.img, cv2.COLOR_BGR2RGB)
            full_mask = self.masking_model(img_rgb)
            
            orig_h, orig_w = self.img.shape[:2]
            if full_mask.shape[:2] != (orig_h, orig_w):
                full_mask = cv2.resize(full_mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
                
            if full_mask.dtype != np.uint8:
                full_mask = (full_mask * 255).astype(np.uint8) if full_mask.max() <= 1.0 else full_mask.astype(np.uint8)
                
            _, full_mask = cv2.threshold(full_mask, 100, 255, cv2.THRESH_BINARY)
            self.process_finished.emit(full_mask)

        except Exception as e:
            print(f"Masking error: {e}")
            import cv2
            gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
            _, full_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            self.process_finished.emit(full_mask)

class InpaintingWorker(QThread):
    process_finished = Signal(object)
    progress_percent = Signal(int)
    error = Signal(str)

    def __init__(self, inpaint_model, img, boxes_data):
        super().__init__()
        self.inpaint_model = inpaint_model
        self.img = img
        self.boxes_data = boxes_data

    def run(self):
        try:
            import cv2
            import numpy as np
            
            res_img = self.img.copy()
            total = len(self.boxes_data)
            
            for i, (x, y, w, h, mask) in enumerate(self.boxes_data):
                roi = res_img[y:y+h, x:x+w]
                if mask.shape[:2] != (h, w):
                    mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

                try:
                    roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                    inpainted_roi_rgb = self.inpaint_model(roi_rgb, mask)
                    inpainted_roi = cv2.cvtColor(inpainted_roi_rgb, cv2.COLOR_RGB2BGR)
                except Exception as e:
                    print(f"Inpaint error: {e}")
                    mask_np = mask.astype(np.uint8)
                    inpainted_roi = cv2.inpaint(roi, mask_np, 7, cv2.INPAINT_TELEA)

                res_img[y:y+h, x:x+w] = inpainted_roi
                self.progress_percent.emit(int(((i + 1) / total) * 100))
                
            self.process_finished.emit(res_img)
        except Exception as e:
            self.error.emit(str(e))
