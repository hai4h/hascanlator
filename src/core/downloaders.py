# src/core/downloaders.py
from PySide6.QtCore import QThread, Signal
import urllib.request
import zipfile
import io
import os

class FontDownloadWorker(QThread):
    process_finished = Signal(bool, str)

    def run(self):
        try:
            url = "https://dl.dafont.com/dl/?f=anime_ace_bb"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req) as response:
                with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                    fonts_dir = os.path.join(os.getcwd(), "fonts")
                    os.makedirs(fonts_dir, exist_ok=True)
                    for file_info in z.infolist():
                        if file_info.filename.lower().endswith(('.ttf', '.otf')):
                            z.extract(file_info, fonts_dir)
            self.process_finished.emit(True, "Anime Ace BB downloaded and installed successfully!")
        except Exception as e:
            self.process_finished.emit(False, str(e))
