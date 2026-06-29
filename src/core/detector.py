import cv2
from PySide6.QtCore import QRectF

class TextDetector:
    """Fallback OpenCV heuristic detector for text regions."""
    @staticmethod
    def detect_text_regions(image_path):
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None: 
            return []
            
        _, thresh = cv2.threshold(img, 180, 255, cv2.THRESH_BINARY_INV)
        thresh = cv2.medianBlur(thresh, 3)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 25))
        connected = cv2.dilate(thresh, kernel, iterations=1)
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if 200 < (w * h) < 15000 and (h / float(w)) > 0.5:
                pad = 10
                bx, by = max(0, x - pad), max(0, y - pad)
                bw, bh = min(img.shape[1] - bx, w + (pad*2)), min(img.shape[0] - by, h + (pad*2))
                boxes.append(QRectF(bx, by, bw, bh))
        return boxes