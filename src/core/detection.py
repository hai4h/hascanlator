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
            orig_h, orig_w = res_img.shape[:2]

            for i, box_data in enumerate(self.boxes_data):
                bx, by, bw, bh, bmask = box_data[:5]
                bg_is_noisy = box_data[5] if len(box_data) > 5 else True

                if bmask.shape[:2] != (bh, bw):
                    bmask = cv2.resize(bmask, (bw, bh), interpolation=cv2.INTER_NEAREST)

                # FAST PATH: If the background is uniform (not noisy), skip LaMa.
                # LaMa struggles to output pure black/white and leaves visible smudges.
                # OpenCV's Telea inpainting perfectly propagates solid colors without artifacts.
                if not bg_is_noisy:
                    bmask_np = bmask.astype(np.uint8)
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                    telea_mask = cv2.dilate(bmask_np, kernel)

                    inpainted_roi = cv2.inpaint(res_img[by:by+bh, bx:bx+bw], telea_mask, 7, cv2.INPAINT_TELEA)
                    res_img[by:by+bh, bx:bx+bw] = inpainted_roi
                    self.progress_percent.emit(int(((i + 1) / total) * 100))
                    continue

                # 1. Determine a scale to ensure the box fits inside a 512x512 window with margin.
                # We cap the box size to 400x400 to guarantee LaMa always has at least 56px of real background context around it.
                scale = min(1.0, 400.0 / bw, 400.0 / bh)
                context_w = int(512 / scale)
                context_h = int(512 / scale)

                # 2. Find the center of the bounding box and expand outward to grab the context
                cx = bx + bw // 2
                cy = by + bh // 2

                x1 = cx - context_w // 2
                y1 = cy - context_h // 2
                x2 = x1 + context_w
                y2 = y1 + context_h

                # 3. If the context window hits the page edge, pad the full image natively
                pad_l = max(0, -x1)
                pad_t = max(0, -y1)
                pad_r = max(0, x2 - orig_w)
                pad_b = max(0, y2 - orig_h)

                if pad_l > 0 or pad_t > 0 or pad_r > 0 or pad_b > 0:
                    padded_img = cv2.copyMakeBorder(res_img, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REFLECT_101)
                else:
                    padded_img = res_img

                px1 = x1 + pad_l
                py1 = y1 + pad_t
                px2 = x2 + pad_l
                py2 = y2 + pad_t

                # Extract the wide context crop and set up the corresponding mask
                context_crop = padded_img[py1:py2, px1:px2]
                context_mask = np.zeros((context_h, context_w), dtype=np.uint8)

                tx1 = (bx + pad_l) - px1
                ty1 = (by + pad_t) - py1
                context_mask[ty1:ty1+bh, tx1:tx1+bw] = bmask

                # 4. Resize the context map and mask down to exactly 512x512 for the model
                if scale < 1.0:
                    context_crop_512 = cv2.resize(context_crop, (512, 512), interpolation=cv2.INTER_AREA)
                else:
                    context_crop_512 = cv2.resize(context_crop, (512, 512), interpolation=cv2.INTER_LINEAR)
                context_mask_512 = cv2.resize(context_mask, (512, 512), interpolation=cv2.INTER_NEAREST)

                # 5. Execute LaMa Inpainting
                try:
                    context_rgb_512 = cv2.cvtColor(context_crop_512, cv2.COLOR_BGR2RGB)
                    inpainted_512_rgb = self.inpaint_model(context_rgb_512, context_mask_512)
                    inpainted_512 = cv2.cvtColor(inpainted_512_rgb, cv2.COLOR_RGB2BGR)
                except Exception as e:
                    print(f"Inpaint error: {e}")
                    bmask_np = bmask.astype(np.uint8)
                    inpainted_roi = cv2.inpaint(res_img[by:by+bh, bx:bx+bw], bmask_np, 7, cv2.INPAINT_TELEA)
                    res_img[by:by+bh, bx:bx+bw] = inpainted_roi
                    self.progress_percent.emit(int(((i + 1) / total) * 100))
                    continue

                # 6. Resize the 512x512 inpainted result back up to the exact pixel-size of the original context map
                if context_w != 512 or context_h != 512:
                    inpainted_context = cv2.resize(inpainted_512, (context_w, context_h), interpolation=cv2.INTER_CUBIC)
                else:
                    inpainted_context = inpainted_512

                inpainted_box = inpainted_context[ty1:ty1+bh, tx1:tx1+bw]

                # 7. Soft Alpha-Blend the inpainted box back into the main image.
                # This ensures we completely avoid any rectangular boundary artifacts outside the exact text shape.
                _, blend_mask = cv2.threshold(bmask, 127, 255, cv2.THRESH_BINARY)
                blend_mask = cv2.GaussianBlur(blend_mask, (3, 3), 0)
                alpha = (blend_mask / 255.0)[..., np.newaxis]

                bg_roi = res_img[by:by+bh, bx:bx+bw]
                res_img[by:by+bh, bx:bx+bw] = (inpainted_box * alpha + bg_roi * (1 - alpha)).astype(np.uint8)

                self.progress_percent.emit(int(((i + 1) / total) * 100))

            self.process_finished.emit(res_img)
        except Exception as e:
            self.error.emit(str(e))
