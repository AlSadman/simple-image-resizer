# Simple Image Resizer

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)

> A safe Python CLI utility for resizing images by percentage or dimensions with aspect-ratio preservation, batch processing, dry-run preview, and overwrite protection.

---

## Overview

**Simple Image Resizer** is Project #6 in a portfolio of professional Python CLI applications. Built with safety and simplicity in mind, it empowers users to resize single images or entire folders with high precision while guaranteeing source image immutability.

---

## Key Features

- **Strict Aspect-Ratio Preservation**: Never stretches or warps images. Dimensions are calculated proportionally using high-quality resampling (`Pillow.Resampling.LANCZOS`).
- **Flexible Resize Modes**: Resize by exact percentage (`--percent`), target width (`--width`), or target height (`--height`). Exactly one mode is permitted per run.
- **Multiple Input Workflows**:
  - Single file: `photo.jpg`
  - Multi-file arguments: `img1.jpg img2.png img3.webp`
  - Non-recursive batch folder mode: `--folder demo_data`
- **Format & Transparency Safety**: Supports `.jpg`, `.jpeg`, `.png`, `.webp`, and `.bmp` (case-insensitively). Preserves RGBA alpha transparency on PNG files.
- **Dry-Run Preview (`--dry-run`)**: Simulates the exact resizing operation, showing original and final dimensions and destination path without touching the filesystem.
- **Overwrite Protection**: Halts if an output file exists; intentional overwriting requires explicit `--force`.
- **Atomic File Writing**: Resized images are written to a temporary file in the destination folder, checked for structural integrity, and atomically moved into place. No partial or corrupted files are ever left behind.
- **Project Boundary Safety**: Enforces write boundaries within the repository (`C:\SimpleImageResizer`) to prevent accidental filesystem escapes.
- **Source Immutability**: Source files are strictly read-only.
- **Image Metadata Inspection (`--info`)**: Inspect resolution, format, color mode, aspect ratio, and file size without performing a resize.
- **Interactive Mode**: Guided terminal wizard when launched with no CLI arguments.
- **Graceful Interrupts**: Clean `Ctrl+C` handling without messy Python tracebacks (exit code `130`).

---

## Project Structure

```text
C:\SimpleImageResizer
├── src\
│   └── image_resizer.py          # Main CLI application and core engine
├── tests\
│   └── test_image_resizer.py     # Unit test suite covering all features and safety checks
├── demo_data\
│   ├── README.md                 # Description of demo images
│   ├── sample_landscape.jpg      # 1600x900 16:9 test image
│   ├── sample_portrait.jpg       # 900x1600 9:16 test image
│   ├── sample_square.png         # 1000x1000 1:1 test image
│   └── sample_transparent.png    # 800x600 4:3 RGBA transparency test image
├── output\
│   └── README.md                 # Default destination folder for resized images
├── screenshots\
│   └── README.md                 # Visual previews and terminal output docs
├── README.md                     # Documentation
├── requirements.txt              # Pillow dependency
├── .gitignore                    # Git rules ignoring temporary images & caches
└── LICENSE                       # MIT License
```

---

## Installation & Setup

Ensure Python 3.10+ is installed on your system.

```bash
# Navigate to the project root
cd C:\SimpleImageResizer

# Install required dependencies
python -m pip install -r requirements.txt
```

---

## Usage Guide

### 1. View Help Screen

```bash
python src\image_resizer.py --help
```

### 2. Percentage Resizing

```bash
# Resize an image to 50% of its original size
python src\image_resizer.py --input demo_data\sample_landscape.jpg --percent 50

# Double image dimensions (200%)
python src\image_resizer.py --input demo_data\sample_square.png --percent 200
```

### 3. Width-Based Resizing (Aspect Ratio Preserved)

```bash
# Sets width to 800px; height is automatically scaled proportionally
python src\image_resizer.py --input demo_data\sample_landscape.jpg --width 800
```

### 4. Height-Based Resizing (Aspect Ratio Preserved)

```bash
# Sets height to 600px; width is automatically scaled proportionally
python src\image_resizer.py --input demo_data\sample_portrait.jpg --height 600
```

### 5. Multi-File Processing

```bash
python src\image_resizer.py --input demo_data\sample_landscape.jpg demo_data\sample_square.png --percent 75
```

### 6. Batch Folder Mode

```bash
# Process all supported images in demo_data
python src\image_resizer.py --folder demo_data --width 640
```

### 7. Dry-Run Preview

```bash
python src\image_resizer.py --input demo_data\sample_landscape.jpg --percent 50 --dry-run
```

Output:
```text
DRY RUN
Input:     demo_data\sample_landscape.jpg
Original:  1600x900
Resize:    50.0%
New size:  800x450
Output:    output\sample_landscape_resized.jpg
No files were created.
```

### 8. Image Metadata Inspection

```bash
python src\image_resizer.py --input demo_data\sample_landscape.jpg --info
```

Output:
```text
File:         sample_landscape.jpg
Format:       JPEG
Width:        1600
Height:       900
Mode:         RGB
Aspect Ratio: 16:9
File Size:    46,554 bytes
Full Path:    demo_data\sample_landscape.jpg
```

### 9. Custom Suffix and Directory

```bash
python src\image_resizer.py --input demo_data\sample_square.png --percent 50 --suffix _thumb --output output
```
Result: `output\sample_square_thumb.png`

### 10. Overwrite Protection & Force Flag

By default, existing files are protected from overwriting:
```bash
python src\image_resizer.py --input demo_data\sample_landscape.jpg --percent 50
# Error: Output file already exists: 'output\sample_landscape_resized.jpg'. Use --force if you want to replace it.

# To intentionally replace:
python src\image_resizer.py --input demo_data\sample_landscape.jpg --percent 50 --force
```

### 11. Quiet Mode

Reduces stdout output for automation or shell scripts while retaining error reporting:
```bash
python src\image_resizer.py --folder demo_data --percent 50 --quiet --force
```

### 12. Interactive Mode

Launch without arguments to use the interactive wizard:
```bash
python src\image_resizer.py
```

```text
===================================
=== Simple Image Resizer ===
===================================
1. Resize image
2. Resize folder
3. View image information
4. Exit

Choose an option (1-4):
```

---

## Exit Codes

| Exit Code | Meaning |
| :---: | :--- |
| `0` | Success / All files processed successfully |
| `1` | Processing error / One or more files failed |
| `2` | Invalid input, bad configuration, or project boundary violation |
| `130` | Operation cleanly cancelled by user (`Ctrl+C`) |

---

## Testing

Run the test suite using Python's built-in `unittest` runner:

```bash
python -m unittest discover -s tests -v
```

The test suite tests:
- Aspect ratio calculations across percentage, width, and height modes
- Zero and negative value rejections
- Mutual exclusivity of flags
- Source image immutability (bytes, size, and dimensions)
- Dry-run mode non-creation
- Overwrite protection and `--force`
- RGBA transparency retention
- Multi-dot filename suffix handling (`holiday.photo.v1.jpg` -> `holiday.photo.v1_thumb.jpg`)
- Atomic writing and error cleanup of temporary files
- Project boundary enforcement
- Batch folder processing with mixed files and error recovery

---

## License

This project is licensed under the [MIT License](LICENSE).
