import os
import pickle
import tempfile
from collections import OrderedDict

import cv2

from src.core.constants import AppCacheConfig


class BoundedImageCache(OrderedDict):
    def __init__(self, max_entries, spill_dir, workspace_ref, cache_type):
        super().__init__()
        self.max_entries = max_entries
        self.spill_dir = spill_dir
        self.workspace_ref = workspace_ref
        self.cache_type = cache_type

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self.max_entries:
            evicted_key, evicted_val = self.popitem(last=False)
            self.workspace_ref._spill_to_disk(evicted_key, evicted_val, self.cache_type)


class BoundedPageStateCache(OrderedDict):
    """LRU-bounded cache for per-page BoxState lists.

    BoxState objects carry numpy `generated_mask` arrays, so an unbounded
    cache would steadily grow RAM as the user visits more pages. When
    evicted, the entry is simply dropped — `save_current_page_state`
    will rebuild it from the live scene the next time the page is opened
    (the scene reloads boxes from history via `load_history_step`).
    """
    def __init__(self, max_entries):
        super().__init__()
        self.max_entries = max_entries

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self.max_entries:
            self.popitem(last=False)


class WorkspaceManager:
    def __init__(self):
        self.image_paths = []
        self.current_img_index = -1

        self.page_data_cache = BoundedPageStateCache(AppCacheConfig.MAX_IMAGES_IN_RAM)

        self._temp_dir = tempfile.mkdtemp(prefix="hascanlator_")
        self._spilled_images = {}
        self._spilled_history = {}

        self.original_images = BoundedImageCache(AppCacheConfig.MAX_IMAGES_IN_RAM, self._temp_dir, self, "orig")
        self.edited_images = BoundedImageCache(AppCacheConfig.MAX_IMAGES_IN_RAM, self._temp_dir, self, "edit")

        self.history = {}
        self.history_indices = {}

    def _spill_to_disk(self, path, img_to_spill, cache_type):
        """Saves evicted images to disk to free RAM."""
        temp_path = os.path.join(self._temp_dir, f"{hash(path)}_{cache_type}.png")
        # Use fast PNG compression
        cv2.imwrite(temp_path, img_to_spill, [cv2.IMWRITE_PNG_COMPRESSION, 1])

        if path not in self._spilled_images:
            self._spilled_images[path] = {}
        self._spilled_images[path][cache_type] = temp_path

        # Spill history if it exists for this path (only needs to happen once)
        if cache_type == "edit" and path in self.history:
            hist_data = self.history.pop(path)
            hist_idx = self.history_indices.pop(path, -1)
            temp_hist = os.path.join(self._temp_dir, f"{hash(path)}_hist.pkl")
            with open(temp_hist, 'wb') as f:
                pickle.dump({'history': hist_data, 'index': hist_idx}, f)
            self._spilled_history[path] = temp_hist

    def restore_from_disk(self, path):
        """Reloads evicted pages back into RAM when the user navigates back."""
        if path not in self.original_images and path in self._spilled_images:
            paths = self._spilled_images.get(path, {})
            if 'orig' in paths and os.path.exists(paths['orig']):
                self.original_images[path] = cv2.imread(paths['orig'])
                os.remove(paths['orig'])

            if 'edit' in paths and os.path.exists(paths['edit']):
                self.edited_images[path] = cv2.imread(paths['edit'])
                os.remove(paths['edit'])

            # Cleanup tracking dict if both are restored
            if 'orig' not in paths and 'edit' not in paths:
                del self._spilled_images[path]

        if path not in self.history and path in self._spilled_history:
            hist_file = self._spilled_history[path]
            if os.path.exists(hist_file):
                with open(hist_file, 'rb') as f:
                    data = pickle.load(f)
                self.history[path] = data['history']
                self.history_indices[path] = data['index']
                os.remove(hist_file)
            del self._spilled_history[path]

    def load_images(self, file_paths):
        self.image_paths = sorted(file_paths)
        self.current_img_index = 0
        self.page_data_cache.clear()

    def reset(self):
        self.image_paths.clear()
        self.current_img_index = -1
        self.page_data_cache.clear()
        self.original_images.clear()
        self.edited_images.clear()
        self.history.clear()
        self.history_indices.clear()

        # Clean up disk spill
        for f in os.listdir(self._temp_dir):
            os.remove(os.path.join(self._temp_dir, f))
        self._spilled_images.clear()
        self._spilled_history.clear()

    @property
    def has_images(self): return len(self.image_paths) > 0

    @property
    def current_image_path(self):
        if self.has_images and 0 <= self.current_img_index < len(self.image_paths):
            return self.image_paths[self.current_img_index]
        return None

    @property
    def current_filename(self):
        return os.path.basename(self.current_image_path) if self.current_image_path else ""

    @property
    def total_pages(self): return len(self.image_paths)

    @property
    def current_page_number(self): return self.current_img_index + 1

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
        if path: self.page_data_cache[path] = boxes_data

    def get_page_state(self, path): return self.page_data_cache.get(path, None)

    def is_page_processed(self, path): return path in self.page_data_cache
