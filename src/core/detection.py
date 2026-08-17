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
            # Spatial grid: clusters are bucketed into 128px cells; only clusters sharing a cell
            # with a new box are tested (exact tests unchanged), turning O(n^2) into ~O(n).
            CELL = 128

            # Manga text is vertical, meaning lines are separated horizontally (X-axis).
            # Lowered x_margin to avoid jumping across distinct bubbles.
            x_margin = 12
            y_margin = 0

            def _cell_range(rect):
                x0, y0 = int(rect.left()) // CELL, int(rect.top()) // CELL
                x1, y1 = int(rect.right()) // CELL, int(rect.bottom()) // CELL
                return x0, y0, x1, y1

            merged_boxes = []   # QRectF or None (merged away); indices stable
            grid = {}           # (cx, cy) -> set of cluster indices

            def _unregister(idx, rect=None):
                if rect is None:
                    rect = merged_boxes[idx]
                x0, y0, x1, y1 = _cell_range(rect)
                for cy in range(y0, y1 + 1):
                    for cx in range(x0, x1 + 1):
                        grid.get((cx, cy), set()).discard(idx)

            def _register(idx):
                rect = merged_boxes[idx]
                x0, y0, x1, y1 = _cell_range(rect)
                for cy in range(y0, y1 + 1):
                    for cx in range(x0, x1 + 1):
                        grid.setdefault((cx, cy), set()).add(idx)

            for box in raw_boxes:
                matched_clusters = []
                expanded_box = box.adjusted(-x_margin, -y_margin, x_margin, y_margin)

                # Candidates: clusters in any cell the expanded box covers (provably complete:
                # an intersecting cluster shares a point p with the expanded range, and cell(p)
                # is within the queried cell span). Exact tests still run on every candidate.
                candidates = set()
                x0, y0, x1, y1 = _cell_range(expanded_box)
                for cy in range(y0, y1 + 1):
                    for cx in range(x0, x1 + 1):
                        candidates.update(grid.get((cx, cy), ()))

                for idx in candidates:
                    cluster = merged_boxes[idx]
                    # Ultra-Strict Heuristic: Lines in the same bubble are highly aligned vertically.
                    # Require at least 60% vertical overlap to fuse them. This prevents diagonal/staggered
                    # bubbles from merging just because their corners touch.
                    overlap_top = max(box.top(), cluster.top())
                    overlap_bottom = min(box.bottom(), cluster.bottom())
                    overlap_height = max(0, overlap_bottom - overlap_top)

                    min_height = min(box.height(), cluster.height())

                    if expanded_box.intersects(cluster) and (overlap_height / max(1.0, min_height)) > 0.60:
                        matched_clusters.append(idx)

                if not matched_clusters:
                    merged_boxes.append(box)
                    _register(len(merged_boxes) - 1)
                else:
                    first_idx = sorted(matched_clusters)[0]
                    first_rect = merged_boxes[first_idx]
                    merged_boxes[first_idx] = first_rect.united(box)
                    # If the new box bridges multiple existing clusters, merge them all into the first one
                    for idx in sorted(matched_clusters)[1:]:
                        merged_boxes[first_idx] = merged_boxes[first_idx].united(merged_boxes[idx])
                        _unregister(idx)
                        merged_boxes[idx] = None
                    _unregister(first_idx, first_rect)
                    _register(first_idx)

            merged_boxes = [b for b in merged_boxes if b is not None]

            self.process_finished.emit(merged_boxes)
        except Exception as e:
            self.error.emit(str(e))


class MaskingWorker(QThread):
    process_finished = Signal(object)
    error = Signal(str)

    def __init__(self, masking_model, img, orig_img, boxes_data):
        super().__init__()
        self.masking_model = masking_model
        self.img = img
        self.orig_img = orig_img
        self.boxes_data = boxes_data

    def run(self):
        import cv2
        import numpy as np

        try:
            img_rgb = cv2.cvtColor(self.img, cv2.COLOR_BGR2RGB)
            full_mask = self.masking_model(img_rgb)

            orig_h, orig_w = self.img.shape[:2]
            if full_mask.shape[:2] != (orig_h, orig_w):
                full_mask = cv2.resize(full_mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)

            if full_mask.dtype != np.uint8:
                full_mask = (full_mask * 255).astype(np.uint8) if full_mask.max() <= 1.0 else full_mask.astype(np.uint8)

            _, full_mask = cv2.threshold(full_mask, 100, 255, cv2.THRESH_BINARY)
            self.process_finished.emit(self._analyze_boxes(full_mask))

        except Exception as e:
            print(f"Masking error: {e}")
            try:
                gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
                _, full_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                self.process_finished.emit(self._analyze_boxes(full_mask))
            except Exception as e2:
                self.error.emit(str(e2))

    def _analyze_boxes(self, full_mask):
        """Per-box ROI extraction + background classification (runs off the UI thread)."""
        import cv2
        import numpy as np

        orig_img = self.orig_img
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        kernel_bg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        kernel_expand = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

        results = []
        for x, y, w, h, box_ref in self.boxes_data:
            raw_mask_roi = full_mask[y:y+h, x:x+w].copy()

            mask_roi = cv2.dilate(raw_mask_roi, kernel, iterations=3)

            # --- CLASSIFY BUBBLE VS FLOATING TEXT ---
            roi_img = orig_img[y:y+h, x:x+w]

            is_bubble = True
            bg_is_noisy = False
            is_solid = False
            bg_mean = 255.0

            if roi_img.size > 0:
                gray_roi = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)

                # Expand the text mask by 4 pixels to guarantee we completely cover
                # the Japanese text and its anti-aliasing
                text_mask = cv2.dilate(raw_mask_roi, kernel_bg)
                bg_mask = cv2.bitwise_not(text_mask)

                bg_pixels = gray_roi[bg_mask > 127]

                if len(bg_pixels) > 0:
                    bg_mean = float(np.mean(bg_pixels))
                    bg_std = float(np.std(bg_pixels))

                    # 1. Edge Detection (Detects drawing lines, panel borders, picture frames)
                    edges = cv2.Canny(gray_roi, 50, 150)
                    bg_edges = edges[bg_mask > 127]

                    # If even 1% of the background consists of strong edges/lines, it is drawn art.
                    edge_ratio = np.sum(bg_edges > 0) / len(bg_pixels)

                    # 2. Strict Uniformity Checks
                    white_ratio = np.sum(bg_pixels > 230) / len(bg_pixels)
                    black_ratio = np.sum(bg_pixels < 25) / len(bg_pixels)

                    # A solid background has near zero standard deviation (e.g. pure white, black, or flat gray)
                    is_solid = bool(bg_std < 5.0 or white_ratio > 0.95 or black_ratio > 0.95)

                    # A clean bubble/box has very few sharp internal drawn lines
                    is_clean_box = bool(edge_ratio < 0.01)

                    # --- MASK ENHANCEMENT FOR DARK BACKGROUNDS ---
                    # White text blooms heavily on dark backgrounds. We aggressively dilate
                    # the mask so inpainting doesn't smudge unmasked white halos.
                    if bg_mean < 100:
                        mask_roi = cv2.dilate(mask_roi, kernel_expand, iterations=2)

                    is_bubble = is_clean_box
                    bg_is_noisy = not is_clean_box

            results.append({
                "box": box_ref,
                "mask": mask_roi,
                "bg_mean": bg_mean,
                "is_bubble": is_bubble,
                "bg_is_noisy": bg_is_noisy,
                "is_solid": is_solid,
            })

        return results

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
                is_solid = box_data[5] if len(box_data) > 5 else False

                if bmask.shape[:2] != (bh, bw):
                    bmask = cv2.resize(bmask, (bw, bh), interpolation=cv2.INTER_NEAREST)

                # FAST PATH: If the background is strictly uniform (pure solid color), skip LaMa.
                # OpenCV's Telea inpainting perfectly propagates solid colors without artifacts.
                # Gradients, screentones, and noisy art should route to LaMa.
                if is_solid:
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

                # Clear ONNX tensor references between loops (refcount handles the memory)
                del context_crop, context_mask, context_crop_512, context_mask_512
                del inpainted_512, inpainted_context, inpainted_box, blend_mask, alpha, bg_roi

            self.process_finished.emit(res_img)
        except Exception as e:
            self.error.emit(str(e))
