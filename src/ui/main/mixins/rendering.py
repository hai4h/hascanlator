from src.core.box_state import BoxState
from src.ui.canvas.items import BoundingBoxItem
from PySide6.QtWidgets import QGraphicsPixmapItem
from PySide6.QtCore import QRectF, Qt, QTimer

class RenderingMixin:
    def __init__(self):
        # Navigation debounce timer to prevent UI flooding
        self._nav_timer = QTimer(self)
        self._nav_timer.setSingleShot(True)
        self._nav_timer.setInterval(100)  # 150ms delay
        self._nav_timer.timeout.connect(self._execute_navigation)
        self._desired_page = -1

    def load_images_dialog(self):
        from PySide6.QtWidgets import QFileDialog
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Manga Pages", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_paths:
            self.workspace.load_images(file_paths)
            self.render_current_page()

    def reset_workspace(self):
        self.workspace.reset()
        self.current_image_item = None
        self.scene.clear()
        self.nav.update_labels(0, 0)
        self.history_dock.history_list.clear()
        self.update_window_title()
        self.update_button_states()
        self.statusBar().showMessage("Workspace Reset")

    def _schedule_navigation(self, target_idx):
        """Queues a navigation request. Resets timer if called rapidly."""
        self._desired_page = max(0, min(self.workspace.total_pages - 1, target_idx))
        self._nav_timer.start()

    def _execute_navigation(self):
        """Fires after user stops clicking. Saves the OLD page and renders the NEW page."""
        if self._desired_page == -1 or self._desired_page == self.workspace.current_img_index:
            return

        # Save state of the page we are actually leaving
        self.save_current_page_state()

        # Update index to the desired page
        self.workspace.current_img_index = self._desired_page

        # Render it
        self.render_current_page()

    def render_current_page(self):
        # Keep desired_page in sync if navigation happens programmatically
        self._desired_page = self.workspace.current_img_index

        if not self.workspace.has_images: return
        path = self.workspace.current_image_path

        # Restore from disk if evicted by LRU cache
        self.workspace.restore_from_disk(path)

        self.nav.update_labels(self.workspace.current_page_number, self.workspace.total_pages)
        self.scene.clear()

        if path not in self.workspace.original_images:
            cv_img = self.imread_utf8(path)
            self.workspace.original_images[path] = cv_img.copy()
            self.workspace.edited_images[path] = cv_img.copy()
            self.workspace.history[path] = []
            self.workspace.history_indices[path] = -1

        pixmap = self.cv2_to_qpixmap(self.workspace.edited_images[path])
        self.current_image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.current_image_item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.view.setFocus()

        cached_data = self.workspace.get_page_state(path)
        if cached_data:
            for state in cached_data:
                box = BoundingBoxItem(state.rect, is_auto=state.is_auto)
                state.apply_to(box)
                self.scene.addItem(box)

        if path not in self.workspace.history or not self.workspace.history[path]:
            self.commit_history("Initial State")
        else:
            self._refresh_history_ui()

        self.update_window_title()
        self.update_button_states()

        if not self.workspace.is_page_processed(path) and self.toolbar.chk_auto_process.isChecked() and self.yolo_model:
            QTimer.singleShot(100, self.run_auto_detect)

    def jump_to_image(self, target_idx):
        if not self.is_processing and self.workspace.has_images:
            if 0 <= target_idx < self.workspace.total_pages and target_idx != self.workspace.current_img_index:
                self._schedule_navigation(target_idx)
            else:
                self.nav.update_labels(self.workspace.current_page_number, self.workspace.total_pages)

    def prev_image(self):
        if not self.is_processing:
            self._schedule_navigation(self.workspace.current_img_index - 1)

    def next_image(self):
        if not self.is_processing:
            self._schedule_navigation(self.workspace.current_img_index + 1)
