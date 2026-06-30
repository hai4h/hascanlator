# HAScanlator

Half-A$$ Scanlator is a local desktop application designed to streamline the manga scanlation process. It features automated text detection, optical character recognition (OCR), and an interactive workspace for manual refinement.

## Features
* Modular machine learning architecture (CPU/GPU supported)
* Automated speech bubble detection (YOLOv8)
* Vertical Japanese text recognition (MangaOCR)
* Non-destructive, interactive bounding box workspace
* Multi-page project state persistence
* Soon to implement: PDF exporter, automated start-to-end translation, SLM refining option

## Installation
1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt` or sequently run every lines in `pip-install.txt`
3. Run the application: `python run.py`