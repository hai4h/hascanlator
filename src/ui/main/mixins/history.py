from src.core.box_state import BoxState
from src.ui.canvas.items import BoundingBoxItem
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsPixmapItem

class HistoryMixin:
    def get_current_boxes_state(self):
        return [BoxState.from_item(item) for item in self.scene.items() if isinstance(item, BoundingBoxItem)]

    def save_current_page_state(self):
        if not self.workspace.current_image_path: return
        boxes = self.get_current_boxes_state()
        self.workspace.save_page_state(self.workspace.current_image_path, boxes)

    def commit_history(self, desc, aggregate=False):
        path = self.workspace.current_image_path
        if not path: return
        img = self.workspace.edited_images[path].copy()
        boxes = self.get_current_boxes_state()

        if path not in self.workspace.history:
            self.workspace.history[path] = []
            self.workspace.history_indices[path] = -1

        curr_idx = self.workspace.history_indices[path]
        if curr_idx < len(self.workspace.history[path]) - 1:
            self.workspace.history[path] = self.workspace.history[path][:curr_idx + 1]

        if aggregate and curr_idx >= 0:
            if self.workspace.history[path][curr_idx]['desc'] == desc:
                self.workspace.history[path][curr_idx]['boxes'] = boxes
                self.workspace.history[path][curr_idx]['image'] = img
                self._refresh_history_ui()
                self.update_button_states()
                return

        self.workspace.history[path].append({'desc': desc, 'image': img, 'boxes': boxes})
        self.workspace.history_indices[path] = len(self.workspace.history[path]) - 1
        self._refresh_history_ui()
        self.update_button_states()

    def _refresh_history_ui(self):
        path = self.workspace.current_image_path
        self.history_dock.history_list.blockSignals(True)
        self.history_dock.history_list.clear()
        if path and path in self.workspace.history:
            curr_idx = self.workspace.history_indices.get(path, -1)
            for idx, step in enumerate(self.workspace.history[path]):
                self.history_dock.history_list.addItem(f"{idx + 1}. {step['desc']}")
                if idx > curr_idx:
                    item = self.history_dock.history_list.item(idx)
                    item.setForeground(QColor("gray"))
                    f = item.font(); f.setItalic(True); item.setFont(f)
            if curr_idx >= 0: self.history_dock.history_list.setCurrentRow(curr_idx)
        self.history_dock.history_list.blockSignals(False)

    def on_history_item_clicked(self, item):
        self.load_history_step(self.history_dock.history_list.row(item))

    def load_history_step(self, index):
        path = self.workspace.current_image_path
        if not path or path not in self.workspace.history: return
        history_list = self.workspace.history[path]
        if index < 0 or index >= len(history_list): return

        self.set_processing_lock(True)
        step = history_list[index]
        self.workspace.edited_images[path] = step['image'].copy()
        self.workspace.history_indices[path] = index

        self.scene.clear()
        pixmap = self.cv2_to_qpixmap(self.workspace.edited_images[path])
        self.current_image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.current_image_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        # Restore using BoxState (Eliminates 40 lines of dict mapping)
        for state in step['boxes']:
            box = BoundingBoxItem(state.polygon, is_auto=state.is_auto, shape_type=state.shape_type)
            state.apply_to(box)
            self.scene.addItem(box)

        self._refresh_history_ui()
        self.set_processing_lock(False)
        self.update_button_states()