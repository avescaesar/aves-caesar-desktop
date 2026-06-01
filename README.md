# Aves Caesar

![Aves Caesar](https://www.aves-caesar.com/assets/classification.png)

[![Version](https://img.shields.io/badge/version-0.1.21-blue)](package.json)
[![License: AGPL v3+](https://img.shields.io/badge/license-AGPL--3.0--or--later-green)](LICENSE.txt)
[![Windows](https://img.shields.io/badge/platform-Windows-0078D4)](https://www.aves-caesar.com)
[![Local inference](https://img.shields.io/badge/inference-local-orange)](#privacy)

**Aves Caesar** is a free and open source desktop app for identifying birds in your photos, browsing photo collections, organizing images by species, and adding species keywords in Lightroom Classic.

The app runs bird detection and classification locally on your computer with ONNX models. Your photos are not sent to a cloud service for identification.

- Website: [www.aves-caesar.com](https://www.aves-caesar.com)
- License: [AGPL-3.0-or-later](LICENSE.txt)

## Features

- Identification of **10,859 bird species**.
- Detection of multiple birds in the same photo, followed by separate classification of each detected area.
- Readable results with species name, scientific name, confidence score, and plausible alternatives.
- Optional use of GPS coordinates, capture date, and GPX tracks.
- Manual corrections saved locally.
- Full photo collection scanning with cached predictions and thumbnails.
- Automatic organization by species, by copying files into a destination folder.
- Lightroom Classic plugin for applying hierarchical `Aves Caesar > species` keywords.
- Interface available in French, English, German, and Spanish.

## Screenshots

| Identification | Collection | Organization |
| --- | --- | --- |
| ![Bird identification in Aves Caesar](https://www.aves-caesar.com/assets/classification.png) | ![Aves Caesar collection view](https://www.aves-caesar.com/assets/collection.png) | ![Aves Caesar automatic organization view](https://www.aves-caesar.com/assets/organization.png) |

## Reliability

GPS coordinates help the app choose between visually similar species. Without GPS, Aves Caesar relies on the image alone and still performs well.

| Context | Species top-1 | Species top-5 | Family |
| --- | ---: | ---: | ---: |
| With GPS | 95.46% | 99.09% | 99.27% |
| Without GPS | 89.78% | 97.56% | 98.86% |

These figures come from internal tests on 100s of thousands of pictures.

## Running locally

Aves Caesar is built to run locally:

- ONNX models run on your machine;
- photos are not sent to the Internet for identification;

## Supported Formats

Aves Caesar supports JPEG, HEIC, and several common RAW formats, including:

```text
DNG, CR2, CR3, NEF, ARW, RW2, ORF, RAF
```


## Development Setup

Requirements:

- Windows
- Python 3.11 or newer
- Node.js and npm

Install and run the full app:

```powershell
npm install
npm start
```

`npm start` prepares the Python environment when needed, installs platform-specific Python dependencies, installs ExifTool into `resources/exiftool/`, builds the frontend, and starts the pywebview app.

`npm run dev` starts Vite for frontend-only work. Before launching the Python backend directly, run `npm run build`, because the app loads `frontend/dist/index.html`.

## Model Files

Model files are not versioned in this repository. Development runs load models from `models/`.
Release builds read [model-version.json](model-version.json), download the configured Hugging Face revision, and stage the bundle in `resources/models/` before packaging.

To run predictions locally, place these files in `models/`:

```text
models/bird_detector.onnx
models/bird_classifier.onnx
models/bird_classifier.onnx.data
models/species_mapping_v2.csv
models/model_performance.json
```

To prepare the packaged model bundle manually:

```powershell
.venv\Scripts\python.exe scripts\models\download_release_models.py
```

The script writes `resources/models/model-build-info.json`, which the installed app exposes in version/debug details.

Runtime settings are stored in [runtime_config.json](runtime_config.json) at the repository root.

Important settings:

- `provider_preference`: `auto`, `directml`, `coreml`, or `cpu`.
- `detector_batch_size`: number of full images sent to the detector in batch workflows.
- `classifier_batch_size`: number of detected crops sent to the classifier in batch workflows.

## Lightroom Classic

The app starts a local Lightroom bridge server when the desktop shell launches. The Lightroom view can install or uninstall the plugin in the user's Lightroom Classic `Modules` directory.

The plugin can apply hierarchical `Aves Caesar > species` keywords to:

- selected photos;
- the active folder;
- the entire catalog.

When changing the Lua plugin, increment the plugin version in both files:

```text
backend/bird_desktop/lightroom/lua/Info.lua
backend/bird_desktop/lightroom/lua/AvesPlugin.lua
```

Restart Lightroom Classic after installing, uninstalling, or updating the plugin.

## Packaging

Build the Windows app:

```powershell
.venv\Scripts\python.exe scripts\packaging\package.py --platform windows
```

Build the Windows app and installer:

```powershell
.venv\Scripts\python.exe scripts\packaging\package.py --platform windows --install
```

The first command produces the PyInstaller app in `dist/AvesCaesar`. The second also generates the Inno Setup installer in `dist/installer`.

macOS packaging must be run on macOS:

```bash
python scripts/packaging/package.py --platform macos
```

Before packaging, run `scripts\models\download_release_models.py` so `resources/models/` contains the release model files and `model-build-info.json`.

The packaging script prepares ExifTool, includes required resources, and increments the patch version in `package.json`, `package-lock.json`, and `backend/bird_desktop/__init__.py`.

## Ignored Local Data

These directories contain development files, cache data, build output, or external binaries. They should not be committed:

```text
models/
resources/exiftool/
resources/models/
frontend/dist/
build/
dist/
logs/
cache/
```

## License

Aves Caesar is distributed under the **GNU Affero General Public License v3.0 or later**.

Third-party components remain under their own licenses. See:

- [LICENSE.txt](LICENSE.txt)
- [LICENSES/AGPL-3.0-or-later.txt](LICENSES/AGPL-3.0-or-later.txt)
- [LICENSES/THIRD-PARTY-NOTICES.txt](LICENSES/THIRD-PARTY-NOTICES.txt)
- [LICENSES/DATA-SOURCES-NOTICE.txt](LICENSES/DATA-SOURCES-NOTICE.txt)
