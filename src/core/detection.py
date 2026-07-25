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
