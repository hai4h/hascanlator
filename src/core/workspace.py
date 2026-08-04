# src/core/workspace.py
import os
import tempfile
import cv2
import pickle
from collections import OrderedDict
from src.core.constants import AppCacheConfig

class BoundedImageCache(OrderedDict):
    def __init__(self, max_entries, spill_dir, workspace_ref):
        super().__init__()
        self.max_entries = max_entries
        self.spill_dir = spill_dir
        self.workspace_ref = workspace_ref

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        
        while len(self) > self.max_entries:
            evicted_key, _ = self.popitem(last=False)
            self.workspace_ref._spill_to_disk(evicted_key)

class WorkspaceManager:
    def __init__(self):
        self.image_paths = []
        self.current_img_index = -1
        self.page_data_cache = {}

        self._temp_dir = tempfile.mkdtemp(prefix="hascanlator_")
        self._spilled_images = {}  # path -> temp file path
        self._spilled_history = {} # path -> temp file path
        
        self.original_images = BoundedImageCache(AppCacheConfig.MAX_IMAGES_IN_RAM, self._temp_dir, self)
        self.edited_images = BoundedImageCache(AppCacheConfig.MAX_IMAGES_IN_RAM, self._temp_dir, self)
        
        self.history = {}
        self.history_indices = {}

    def _spill_to_disk(self, path):
        """Saves evicted images and history to disk to free RAM."""
        if path in self.original_images:
            orig_img = self.original_images.pop(path)
            temp_orig = os.path.join(self._temp_dir, f"{hash(path)}_orig.png")
            cv2.imwrite(temp_orig, orig_img)
            self._spilled_images[path] = temp_orig
            
        if path in self.edited_images:
            edit_img = self.edited_images.pop(path)
            temp_edit = os.path.join(self._temp_dir, f"{hash(path)}_edit.png")
            cv2.imwrite(temp_edit, edit_img)
            self._spilled_images[path] = temp_edit
            
        if path in self.history:
            hist_data = self.history.pop(path)
            hist_idx = self.history_indices.pop(path, -1)
            temp_hist = os.path.join(self._temp_dir, f"{hash(path)}_hist.pkl")
            with open(temp_hist, 'wb') as f:
                pickle.dump({'history': hist_data, 'index': hist_idx}, f)
            self._spilled_history[path] = temp_hist

    def restore_from_disk(self, path):
        """Reloads evicted pages back into RAM when the user navigates back."""
        if path not in self.original_images and path in self._spilled_images:
            # In a real implementation, you'd use your utf8 imread helper here
            self.original_images[path] = cv2.imread(self._spilled_images[path])
            self.edited_images[path] = cv2.imread(self._spilled_images[path])
            
        if path not in self.history and path in self._spilled_history:
            with open(self._spilled_history[path], 'rb') as f:
                data = pickle.load(f)
            self.history[path] = data['history']
            self.history_indices[path] = data['index']

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