import os

class WorkspaceManager:
    """Manages loaded images, current page index, and bounding box state caching."""
    def __init__(self):
        self.image_paths = []
        self.current_img_index = -1
        self.page_data_cache = {}

    def load_images(self, file_paths):
        self.image_paths = sorted(file_paths)
        self.current_img_index = 0
        self.page_data_cache.clear()

    def reset(self):
        self.image_paths.clear()
        self.current_img_index = -1
        self.page_data_cache.clear()

    @property
    def has_images(self):
        return len(self.image_paths) > 0

    @property
    def current_image_path(self):
        if self.has_images and 0 <= self.current_img_index < len(self.image_paths):
            return self.image_paths[self.current_img_index]
        return None

    @property
    def current_filename(self):
        if self.current_image_path:
            return os.path.basename(self.current_image_path)
        return ""

    @property
    def total_pages(self):
        return len(self.image_paths)

    @property
    def current_page_number(self):
        return self.current_img_index + 1

    def next_page(self):
        if self.current_img_index < self.total_pages - 1:
            self.current_img_index += 1
            return True
        return False

    def prev_page(self):
        if self.current_img_index > 0:
            self.current_img_index -= 1
            return True
        return False

    def save_page_state(self, path, boxes_data):
        """Saves a dictionary of bounding box coordinates/text for a specific image path."""
        if path:
            self.page_data_cache[path] = boxes_data

    def get_page_state(self, path):
        """Retrieves the cached bounding boxes for an image path."""
        return self.page_data_cache.get(path, None)

    def is_page_processed(self, path):
        return path in self.page_data_cache