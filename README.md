# HAScanlator (ON-GOING)

Half-A$$ Scanlator is a local desktop application designed to make the manga scanlation process faster and easier. It provides a complete toolset to detect text, translate it, erase the original Japanese text from the image, and typeset the new translation, all within an interactive workspace.

## Features
* Automated Pipeline: Run detection, OCR, translation, text erasing, and typesetting in a single sequence.
* Speech Bubble Detection: Automatically locates text regions using YOLOv8.
* Text Recognition (OCR): Accurately reads vertical and horizontal Japanese text using MangaOCR.
* Translation Options: Translate text using the online Google Translate API or work entirely offline using local NMT models (Helsinki-NLP or NLLB).
* Text Removal (Inpainting): Automatically generates highly accurate text masks and seamlessly redraws the background behind the text using local ONNX AI models (Comic Text Detector and LaMa).
* Built-in Typesetting: Customize fonts, text size, alignment, line spacing, text color, and outlines directly on the canvas.
* Portable Model Manager: Download AI models directly through the application settings. Models are saved locally in the project folder, making the app easy to move between computers.
* Interactive Workspace: Manually adjust bounding boxes, undo and redo actions, and save your progress across multiple pages.

## Installation (Python 3.12+ recommended, tested with Python 3.14.6)
1. Clone or download this repository.
2. Install the required dependencies. It is recommended to open your terminal and run the installation commands listed inside the `pip-install.txt` file one by one.
3. Start the application by running: `python run.py`
4. Open the Settings menu inside the app to download and load the AI models you want to use.

## Planned Features
* PDF or CBZ exporter
* Large Language Model (LLM) translation refining options

## Acknowledgements
This project relies on several incredible open-source models and repositories. A huge thank you to the following creators and teams:

* **MangaOCR** by [kha-white](https://github.com/kha-white)
* **Manga Image Translator** by [zyddnys](https://github.com/zyddnys) and contributors
* **Comic Text Detector** by [dmMaze](https://github.com/dmMaze)
* **LaMa (Resolution-robust Large Mask Inpainting)** by [advimman](https://github.com/advimman) and [Carve](https://huggingface.co/Carve) for providing the ONNX version
* **YOLOv8 Manga Text Detector** by [ogkalu](https://huggingface.co/ogkalu)
* **Opus-MT** by [Helsinki-NLP](https://huggingface.co/Helsinki-NLP) and **NLLB** by [Meta](https://ai.meta.com/)
* **Anime Ace BB** by [Nate Piekos (Blambot)](https://blambot.com/)
