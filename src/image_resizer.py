#!/usr/bin/env python3
"""
Simple Image Resizer - A safe Python CLI utility for resizing images.

Features:
- Percentage, width, or height resizing with strict aspect ratio preservation.
- Individual files, multi-file arguments, or batch folder processing.
- Mutually exclusive resize options (--percent, --width, --height).
- Dry-run preview mode (--dry-run).
- Overwrite protection with optional override (--force).
- Image metadata inspection (--info).
- Safe atomic writing to prevent corrupted partial files.
- Project boundary safety verification preventing unintended directory escape.
- Quiet mode for script automation.
- Interactive mode for beginner-friendly guided prompts.
- Clean Ctrl+C handling (exit code 130).
"""

import argparse
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from PIL import Image
except ImportError:
    print("Error: The 'Pillow' library is required to run Simple Image Resizer.", file=sys.stderr)
    print("Please install it using: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

# Supported image extensions (case-insensitive)
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Project Root Anchor
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_aspect_ratio_string(width: int, height: int) -> str:
    """Calculate and return a clean aspect ratio representation like '16:9' or '4:3'."""
    if width <= 0 or height <= 0:
        return f"{width}:{height}"
    divisor = math.gcd(width, height)
    simplified_w = width // divisor
    simplified_h = height // divisor
    
    # Check for common rounded aspect ratios if numbers are large
    ratio = width / height
    common_ratios = [
        (16 / 9, "16:9"),
        (4 / 3, "4:3"),
        (3 / 2, "3:2"),
        (1 / 1, "1:1"),
        (9 / 16, "9:16"),
        (3 / 4, "3:4"),
        (2 / 3, "2:3"),
        (21 / 9, "21:9"),
    ]
    for target_val, label in common_ratios:
        if abs(ratio - target_val) < 0.015:
            return label

    return f"{simplified_w}:{simplified_h}"


def get_image_info(image_path: Path) -> dict:
    """
    Open an image and extract descriptive metadata.
    
    Raises:
        ValueError: If file is not found or cannot be verified.
        RuntimeError: If Pillow cannot read image data.
    """
    if not image_path.exists():
        raise ValueError(f"File not found: '{image_path}'")
    if not image_path.is_file():
        raise ValueError(f"Path is not a regular file: '{image_path}'")

    ext = image_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image format: '{ext}' for file '{image_path.name}'")

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            format_name = img.format or ext.lstrip(".").upper()
            mode = img.mode
            aspect_ratio = get_aspect_ratio_string(width, height)
            return {
                "path": str(image_path),
                "filename": image_path.name,
                "format": format_name,
                "width": width,
                "height": height,
                "mode": mode,
                "aspect_ratio": aspect_ratio,
                "size_bytes": image_path.stat().st_size,
            }
    except Exception as exc:
        raise RuntimeError(f"Could not open or decode image '{image_path.name}': {exc}")


def display_image_info(image_path: Path) -> bool:
    """Print formatted image information to stdout."""
    try:
        info = get_image_info(image_path)
        print(f"File:         {info['filename']}")
        print(f"Format:       {info['format']}")
        print(f"Width:        {info['width']}")
        print(f"Height:       {info['height']}")
        print(f"Mode:         {info['mode']}")
        print(f"Aspect Ratio: {info['aspect_ratio']}")
        print(f"File Size:    {info['size_bytes']:,} bytes")
        print(f"Full Path:    {info['path']}")
        return True
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        return False


def calculate_new_dimensions(
    orig_width: int,
    orig_height: int,
    percent: Optional[float] = None,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
) -> Tuple[int, int]:
    """
    Calculate new dimensions preserving aspect ratio.
    Exactly one of percent, target_width, target_height must be provided.
    
    Raises:
        ValueError: If constraints are violated or invalid dimensions result.
    """
    provided = [arg is not None for arg in (percent, target_width, target_height)]
    if sum(provided) != 1:
        raise ValueError("Exactly one resize method (percent, width, or height) must be specified.")

    if percent is not None:
        if percent <= 0:
            raise ValueError(f"Percentage must be greater than zero. Received: {percent}")
        factor = percent / 100.0
        new_w = max(1, round(orig_width * factor))
        new_h = max(1, round(orig_height * factor))
        return (new_w, new_h)

    if target_width is not None:
        if target_width <= 0:
            raise ValueError(f"Width must be greater than zero. Received: {target_width}")
        factor = target_width / orig_width
        new_w = target_width
        new_h = max(1, round(orig_height * factor))
        return (new_w, new_h)

    if target_height is not None:
        if target_height <= 0:
            raise ValueError(f"Height must be greater than zero. Received: {target_height}")
        factor = target_height / orig_height
        new_h = target_height
        new_w = max(1, round(orig_width * factor))
        return (new_w, new_h)

    raise ValueError("No valid resize parameter provided.")


def validate_project_boundary(dest_path: Path, project_root: Path = PROJECT_ROOT) -> Path:
    """
    Ensure destination path is within the allowed project boundary.
    
    Raises:
        PermissionError: If path attempts to escape the project boundary.
    """
    resolved_root = project_root.resolve()
    # Resolve dest path (whether it exists or not, resolve parent or full)
    resolved_dest = dest_path.resolve()
    
    try:
        resolved_dest.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(
            f"Safety error: Destination '{dest_path}' is outside the project directory '{resolved_root}'."
        )
    return resolved_dest


def build_output_path(
    source_path: Path,
    output_dir: Path,
    suffix: str = "_resized",
) -> Path:
    """
    Generate output path with suffix inserted before the extension.
    Example: holiday.photo.jpg -> holiday.photo_resized.jpg
    """
    stem = source_path.stem
    ext = source_path.suffix
    new_filename = f"{stem}{suffix}{ext}"
    return output_dir / new_filename


def resize_image_atomic(
    source_path: Path,
    output_path: Path,
    target_dimensions: Tuple[int, int],
    force: bool = False,
    quiet: bool = False,
) -> bool:
    """
    Safely resize an image and write atomically to output_path.
    
    Workflow:
    1. Verify output path does not collide with source path.
    2. Overwrite check unless force is True.
    3. Resize in memory using Pillow Resampling.LANCZOS.
    4. Save to temporary file in same target folder.
    5. Verify temporary image integrity.
    6. Replace atomically with destination path.
    7. Clean up temporary files on error.
    """
    resolved_src = source_path.resolve()
    resolved_out = output_path.resolve()

    # Safety: Cannot overwrite original source
    if resolved_src == resolved_out:
        raise ValueError(f"Output path cannot be identical to source path: '{output_path}'")

    # Overwrite protection
    if resolved_out.exists() and not force:
        raise FileExistsError(
            f"Output file already exists: '{output_path}'.\nUse --force if you want to replace it."
        )

    # Ensure target directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_w, target_h = target_dimensions
    temp_file_path = None

    try:
        # Load and resize in memory
        with Image.open(resolved_src) as img:
            orig_format = img.format
            # Choose appropriate resampling filter
            resample_filter = getattr(Image.Resampling, "LANCZOS", Image.LANCZOS)
            
            # Maintain color profile/mode integrity (RGBA for PNG/WEBP, RGB for JPEG/BMP)
            resized_img = img.resize((target_w, target_h), resample=resample_filter)

            # Create temporary file in same destination directory to ensure atomic os.replace across filesystem
            fd, temp_file_path_str = tempfile.mkstemp(
                dir=output_path.parent,
                prefix="tmp_resize_",
                suffix=output_path.suffix,
            )
            os.close(fd)
            temp_file_path = Path(temp_file_path_str)

            # Determine save format
            save_format = orig_format or output_path.suffix.lstrip(".").upper()
            if save_format.upper() in ("JPG", "JPEG"):
                save_format = "JPEG"
                # If image has alpha channel, convert to RGB for JPEG compatibility without crashing
                if resized_img.mode in ("RGBA", "LA", "P"):
                    resized_img = resized_img.convert("RGB")
                resized_img.save(temp_file_path, format=save_format, quality=95)
            else:
                resized_img.save(temp_file_path, format=save_format)

        # Integrity verification: Open and inspect the temporary image
        with Image.open(temp_file_path) as verify_img:
            actual_w, actual_h = verify_img.size
            if (actual_w, actual_h) != (target_w, target_h):
                raise RuntimeError(
                    f"Integrity check failed: Expected {target_w}x{target_h}, got {actual_w}x{actual_h}"
                )

        # Atomic replacement
        temp_file_path.replace(resolved_out)
        temp_file_path = None  # Replaced successfully

        if not quiet:
            print(f"Resized: {source_path.name} -> {output_path.name} ({target_w}x{target_h})")
        return True

    except Exception as exc:
        # Clean up temporary file if left behind
        if temp_file_path and temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except OSError:
                pass
        raise exc


def process_resize_request(
    source_path: Path,
    output_dir: Path,
    percent: Optional[float] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    suffix: str = "_resized",
    dry_run: bool = False,
    force: bool = False,
    quiet: bool = False,
) -> bool:
    """Validate, calculate, and either preview or execute resizing for a single file."""
    # Validate project boundary for output
    validate_project_boundary(output_dir)

    # Validate image and read metadata
    info = get_image_info(source_path)
    orig_w, orig_h = info["width"], info["height"]

    new_w, new_h = calculate_new_dimensions(
        orig_w, orig_h, percent=percent, target_width=width, target_height=height
    )

    out_path = build_output_path(source_path, output_dir, suffix=suffix)
    validate_project_boundary(out_path)

    if dry_run:
        method_desc = (
            f"{percent}%"
            if percent is not None
            else f"width={width}px"
            if width is not None
            else f"height={height}px"
        )
        print("DRY RUN")
        print(f"Input:     {source_path}")
        print(f"Original:  {orig_w}x{orig_h}")
        print(f"Resize:    {method_desc}")
        print(f"New size:  {new_w}x{new_h}")
        print(f"Output:    {out_path}")
        print("No files were created.")
        return True

    return resize_image_atomic(
        source_path=source_path,
        output_path=out_path,
        target_dimensions=(new_w, new_h),
        force=force,
        quiet=quiet,
    )


def process_folder(
    folder_path: Path,
    output_dir: Path,
    percent: Optional[float] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    suffix: str = "_resized",
    dry_run: bool = False,
    force: bool = False,
    quiet: bool = False,
) -> Tuple[int, int, int]:
    """
    Process all supported image files in a folder non-recursively.
    Returns (completed_count, failed_count, skipped_count).
    """
    if not folder_path.exists():
        raise ValueError(f"Folder not found: '{folder_path}'")
    if not folder_path.is_dir():
        raise ValueError(f"Path is not a directory: '{folder_path}'")

    # Discover and sort supported images alphabetically
    candidates = sorted(folder_path.iterdir(), key=lambda p: p.name.lower())
    image_files = [f for f in candidates if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]

    total = len(image_files)
    if total == 0:
        if not quiet:
            print(f"No supported images found in folder: '{folder_path}'")
        return (0, 0, 0)

    if not quiet:
        print(f"Found {total} supported image{'s' if total != 1 else ''}.\n")
        if not dry_run:
            print("Processing:")

    completed = 0
    failed = 0
    skipped = 0

    for idx, img_file in enumerate(image_files, start=1):
        if not quiet and not dry_run:
            print(f"[{idx}/{total}] {img_file.name}")
        try:
            success = process_resize_request(
                source_path=img_file,
                output_dir=output_dir,
                percent=percent,
                width=width,
                height=height,
                suffix=suffix,
                dry_run=dry_run,
                force=force,
                quiet=quiet,
            )
            if success:
                completed += 1
            else:
                failed += 1
        except FileExistsError as fee:
            failed += 1
            print(f"  Error: {fee}", file=sys.stderr)
        except Exception as exc:
            failed += 1
            print(f"  Error processing '{img_file.name}': {exc}", file=sys.stderr)

    if not quiet:
        print("\nSummary:")
        print(f"Completed: {completed}")
        print(f"Failed:    {failed}")
        print(f"Skipped:   {skipped}")

    return (completed, failed, skipped)


def interactive_mode():
    """Interactive command-line wizard for guided usage."""
    print("=" * 35)
    print("=== Simple Image Resizer ===")
    print("=" * 35)
    print("1. Resize image")
    print("2. Resize folder")
    print("3. View image information")
    print("4. Exit\n")

    try:
        choice = input("Choose an option (1-4): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nOperation cancelled by user.")
        sys.exit(130)

    if choice == "4" or choice.lower() in ("exit", "quit", "q"):
        print("Goodbye!")
        sys.exit(0)

    if choice == "3":
        try:
            target = input("Enter path to image: ").strip()
            if not target:
                print("Error: No file path provided.", file=sys.stderr)
                sys.exit(2)
            p = Path(target)
            success = display_image_info(p)
            sys.exit(0 if success else 1)
        except (EOFError, KeyboardInterrupt):
            print("\nOperation cancelled by user.")
            sys.exit(130)

    if choice not in ("1", "2"):
        print("Error: Invalid selection.", file=sys.stderr)
        sys.exit(2)

    is_folder = choice == "2"

    try:
        target_input = input(f"Enter {'folder' if is_folder else 'image'} path: ").strip()
        if not target_input:
            print("Error: Path cannot be empty.", file=sys.stderr)
            sys.exit(2)

        print("\nResize method:")
        print("1. Percentage")
        print("2. Width")
        print("3. Height")
        method = input("Choose method (1-3): ").strip()

        percent, width, height = None, None, None
        if method == "1":
            raw_val = input("Enter percentage (e.g. 50 for half size): ").strip()
            percent = float(raw_val)
        elif method == "2":
            raw_val = input("Enter target width in pixels (e.g. 800): ").strip()
            width = int(raw_val)
        elif method == "3":
            raw_val = input("Enter target height in pixels (e.g. 600): ").strip()
            height = int(raw_val)
        else:
            print("Error: Invalid resize method selected.", file=sys.stderr)
            sys.exit(2)

        out_dir_raw = input("Enter output directory [default: output]: ").strip()
        output_dir = Path(out_dir_raw) if out_dir_raw else Path("output")

        suffix_raw = input("Enter filename suffix [default: _resized]: ").strip()
        suffix = suffix_raw if suffix_raw else "_resized"

        confirm = input("\nProceed with resizing? (Y/n): ").strip().lower()
        if confirm not in ("", "y", "yes"):
            print("Operation aborted.")
            sys.exit(0)

        if is_folder:
            completed, failed, _ = process_folder(
                folder_path=Path(target_input),
                output_dir=output_dir,
                percent=percent,
                width=width,
                height=height,
                suffix=suffix,
                dry_run=False,
                force=False,
                quiet=False,
            )
            sys.exit(0 if failed == 0 else 1)
        else:
            success = process_resize_request(
                source_path=Path(target_input),
                output_dir=output_dir,
                percent=percent,
                width=width,
                height=height,
                suffix=suffix,
                dry_run=False,
                force=False,
                quiet=False,
            )
            sys.exit(0 if success else 1)

    except ValueError as ve:
        print(f"Error: {ve}", file=sys.stderr)
        sys.exit(2)
    except (EOFError, KeyboardInterrupt):
        print("\nOperation cancelled by user.")
        sys.exit(130)


def create_parser() -> argparse.ArgumentParser:
    """Build and configure the CLI argument parser with comprehensive help."""
    parser = argparse.ArgumentParser(
        prog="image_resizer",
        description="A safe Python CLI utility for resizing images with aspect-ratio preservation, batch processing, dry-run preview, and overwrite protection.",
        epilog=(
            "Examples:\n"
            "  python src/image_resizer.py --input photo.jpg --percent 50\n"
            "  python src/image_resizer.py --input photo.jpg --width 800\n"
            "  python src/image_resizer.py --input photo.jpg --height 600\n"
            "  python src/image_resizer.py --input img1.jpg img2.png --percent 75\n"
            "  python src/image_resizer.py --folder demo_data --percent 50\n"
            "  python src/image_resizer.py --input photo.jpg --percent 50 --dry-run\n"
            "  python src/image_resizer.py --input photo.jpg --info\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Input modes
    input_group = parser.add_argument_group("Input Options")
    input_group.add_argument(
        "-i", "--input",
        nargs="+",
        help="One or more input image file paths to resize.",
    )
    input_group.add_argument(
        "-d", "--folder",
        help="Path to folder of images to process in batch (non-recursive).",
    )

    # Resize methods (mutually exclusive)
    resize_group = parser.add_argument_group("Resize Methods (Choose exactly one)")
    resize_group.add_argument(
        "-p", "--percent",
        type=float,
        help="Resize by percentage (e.g. 50 for 50%%, 200 for 2x).",
    )
    resize_group.add_argument(
        "-w", "--width",
        type=int,
        help="Resize to specific width in pixels (aspect ratio preserved).",
    )
    resize_group.add_argument(
        "-H", "--height",
        type=int,
        help="Resize to specific height in pixels (aspect ratio preserved).",
    )

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "-o", "--output",
        default="output",
        help="Destination directory within project [default: output].",
    )
    output_group.add_argument(
        "-s", "--suffix",
        default="_resized",
        help="Suffix added to filename before extension [default: _resized].",
    )
    output_group.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite existing output files if they already exist.",
    )

    # Operational modifiers
    op_group = parser.add_argument_group("Operations")
    op_group.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Simulate the resize operation without modifying or writing any files.",
    )
    op_group.add_argument(
        "--info",
        action="store_true",
        help="Display dimensions, format, and aspect ratio of input images.",
    )
    op_group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Reduce stdout progress output (errors are still displayed).",
    )

    return parser


def main():
    """Main CLI entrypoint."""
    # If launched with zero arguments, provide interactive mode
    if len(sys.argv) == 1:
        interactive_mode()
        return

    parser = create_parser()
    args = parser.parse_args()

    # Mutual exclusivity check for input sources
    if args.input and args.folder:
        print("Error: Cannot specify both --input and --folder at the same time.", file=sys.stderr)
        sys.exit(2)

    if not args.input and not args.folder:
        print("Error: You must provide either --input or --folder.", file=sys.stderr)
        parser.print_help(sys.stderr)
        sys.exit(2)

    # Inspection info flow
    if args.info:
        targets: List[Path] = []
        if args.folder:
            f_dir = Path(args.folder)
            if not f_dir.exists() or not f_dir.is_dir():
                print(f"Error: Folder not found or invalid: '{args.folder}'", file=sys.stderr)
                sys.exit(2)
            targets = sorted(
                [p for p in f_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS],
                key=lambda p: p.name.lower(),
            )
            if not targets:
                print(f"No supported images found in '{args.folder}'")
                sys.exit(0)
        else:
            for item in args.input:
                p = Path(item)
                if not p.exists():
                    print(f"Error: File not found: '{item}'", file=sys.stderr)
                    sys.exit(2)
                targets.append(p)

        all_ok = True
        for t in targets:
            ok = display_image_info(t)
            if not ok:
                all_ok = False
            if len(targets) > 1:
                print("-" * 30)
        sys.exit(0 if all_ok else 1)

    # Validation: Exactly one resize option must be supplied
    resize_options = [args.percent, args.width, args.height]
    supplied_count = sum(1 for opt in resize_options if opt is not None)
    if supplied_count != 1:
        print(
            "Error: Exactly one resize method is required (--percent, --width, or --height).",
            file=sys.stderr,
        )
        sys.exit(2)

    # Validate numeric ranges
    if args.percent is not None and args.percent <= 0:
        print(f"Error: Percentage must be greater than zero. Received: {args.percent}", file=sys.stderr)
        sys.exit(2)
    if args.width is not None and args.width <= 0:
        print(f"Error: Width must be greater than zero. Received: {args.width}", file=sys.stderr)
        sys.exit(2)
    if args.height is not None and args.height <= 0:
        print(f"Error: Height must be greater than zero. Received: {args.height}", file=sys.stderr)
        sys.exit(2)

    output_dir = Path(args.output)
    try:
        validate_project_boundary(output_dir)
    except PermissionError as pe:
        print(f"Error: {pe}", file=sys.stderr)
        sys.exit(2)

    # Execute folder mode
    if args.folder:
        folder_path = Path(args.folder)
        try:
            completed, failed, _ = process_folder(
                folder_path=folder_path,
                output_dir=output_dir,
                percent=args.percent,
                width=args.width,
                height=args.height,
                suffix=args.suffix,
                dry_run=args.dry_run,
                force=args.force,
                quiet=args.quiet,
            )
            sys.exit(0 if failed == 0 else 1)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(2)

    # Execute individual file(s) mode
    inputs = [Path(p) for p in args.input]
    total_files = len(inputs)
    completed = 0
    failed = 0

    if total_files > 1 and not args.quiet and not args.dry_run:
        print(f"Processing {total_files} images:\n")

    for idx, in_file in enumerate(inputs, start=1):
        if total_files > 1 and not args.quiet and not args.dry_run:
            print(f"[{idx}/{total_files}] {in_file.name}")
        try:
            success = process_resize_request(
                source_path=in_file,
                output_dir=output_dir,
                percent=args.percent,
                width=args.width,
                height=args.height,
                suffix=args.suffix,
                dry_run=args.dry_run,
                force=args.force,
                quiet=args.quiet,
            )
            if success:
                completed += 1
            else:
                failed += 1
        except FileExistsError as fee:
            failed += 1
            print(f"Error: {fee}", file=sys.stderr)
        except Exception as exc:
            failed += 1
            print(f"Error: {exc}", file=sys.stderr)

    if total_files > 1 and not args.quiet:
        print("\nSummary:")
        print(f"Completed: {completed}")
        print(f"Failed:    {failed}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)
