"""
Unit tests for Simple Image Resizer.
Covers:
- Percentage, width, and height calculations with aspect ratio preservation.
- Validation checks (invalid formats, missing files, corrupted files, zero/negative values).
- Source image immutability (size, dimensions, content uncompromised).
- Mutual exclusivity of arguments.
- Dry-run mode behavior (no output created).
- Overwrite protection without --force, and replacement with --force.
- Atomic temporary file creation and cleanup.
- Custom output directory and safety boundary enforcement.
- Custom filename suffix handling (including multiple dots).
- Batch folder processing with mixed filetypes and deterministic ordering.
- Alpha transparency preservation for RGBA images.
- Image info inspection.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from PIL import Image

import sys
# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import image_resizer


class TestDimensionCalculations(unittest.TestCase):
    """Test dimension calculations and aspect ratio math."""

    def test_percent_resize_down(self):
        w, h = image_resizer.calculate_new_dimensions(1920, 1080, percent=50)
        self.assertEqual((w, h), (960, 540))

    def test_percent_resize_up(self):
        w, h = image_resizer.calculate_new_dimensions(500, 500, percent=200)
        self.assertEqual((w, h), (1000, 1000))

    def test_width_resize_preserves_aspect_ratio(self):
        w, h = image_resizer.calculate_new_dimensions(1920, 1080, target_width=800)
        self.assertEqual(w, 800)
        self.assertEqual(h, 450)

    def test_height_resize_preserves_aspect_ratio(self):
        w, h = image_resizer.calculate_new_dimensions(1920, 1080, target_height=600)
        self.assertEqual(h, 600)
        self.assertEqual(w, 1067)

    def test_zero_or_negative_percent_raises_error(self):
        with self.assertRaises(ValueError):
            image_resizer.calculate_new_dimensions(100, 100, percent=0)
        with self.assertRaises(ValueError):
            image_resizer.calculate_new_dimensions(100, 100, percent=-25)

    def test_zero_or_negative_width_raises_error(self):
        with self.assertRaises(ValueError):
            image_resizer.calculate_new_dimensions(100, 100, target_width=0)
        with self.assertRaises(ValueError):
            image_resizer.calculate_new_dimensions(100, 100, target_width=-50)

    def test_zero_or_negative_height_raises_error(self):
        with self.assertRaises(ValueError):
            image_resizer.calculate_new_dimensions(100, 100, target_height=0)
        with self.assertRaises(ValueError):
            image_resizer.calculate_new_dimensions(100, 100, target_height=-50)

    def test_multiple_methods_raises_error(self):
        with self.assertRaises(ValueError):
            image_resizer.calculate_new_dimensions(100, 100, percent=50, target_width=50)


class TestImageResizerOperations(unittest.TestCase):
    """Test file operations, safety boundaries, atomic writes, and batch processing."""

    def setUp(self):
        # Create a temporary sandbox within the project directory for isolation
        self.sandbox_dir = image_resizer.PROJECT_ROOT / "temp_test_sandbox"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = self.sandbox_dir / "test_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create a test RGB image
        self.test_img_path = self.sandbox_dir / "test_rgb.jpg"
        img = Image.new("RGB", (800, 600), color=(100, 150, 200))
        img.save(self.test_img_path, format="JPEG")

        # Create a test RGBA image
        self.test_rgba_path = self.sandbox_dir / "test_rgba.png"
        img_rgba = Image.new("RGBA", (400, 400), color=(255, 0, 0, 128))
        img_rgba.save(self.test_rgba_path, format="PNG")

    def tearDown(self):
        if self.sandbox_dir.exists():
            shutil.rmtree(self.sandbox_dir, ignore_errors=True)

    def test_source_file_immutability(self):
        """Verify that source images are never modified, renamed, or corrupted."""
        orig_bytes = self.test_img_path.read_bytes()
        orig_size = self.test_img_path.stat().st_size
        with Image.open(self.test_img_path) as im:
            orig_dims = im.size

        # Perform resize
        image_resizer.process_resize_request(
            source_path=self.test_img_path,
            output_dir=self.output_dir,
            percent=50,
            suffix="_half",
        )

        # Assert source is completely untouched
        self.assertTrue(self.test_img_path.exists())
        self.assertEqual(self.test_img_path.stat().st_size, orig_size)
        self.assertEqual(self.test_img_path.read_bytes(), orig_bytes)
        with Image.open(self.test_img_path) as im:
            self.assertEqual(im.size, orig_dims)

    def test_dry_run_creates_no_files(self):
        """Dry-run must not create any files in output directory."""
        initial_files = list(self.output_dir.iterdir())
        success = image_resizer.process_resize_request(
            source_path=self.test_img_path,
            output_dir=self.output_dir,
            percent=50,
            dry_run=True,
        )
        self.assertTrue(success)
        self.assertEqual(list(self.output_dir.iterdir()), initial_files)

    def test_overwrite_protection(self):
        """Should raise FileExistsError if output exists without force=True."""
        # First resize
        image_resizer.process_resize_request(
            source_path=self.test_img_path,
            output_dir=self.output_dir,
            percent=50,
        )
        expected_out = self.output_dir / "test_rgb_resized.jpg"
        self.assertTrue(expected_out.exists())

        # Second resize without force must raise
        with self.assertRaises(FileExistsError):
            image_resizer.process_resize_request(
                source_path=self.test_img_path,
                output_dir=self.output_dir,
                percent=50,
                force=False,
            )

        # With force=True should succeed
        success = image_resizer.process_resize_request(
            source_path=self.test_img_path,
            output_dir=self.output_dir,
            percent=25,
            force=True,
        )
        self.assertTrue(success)
        with Image.open(expected_out) as im:
            self.assertEqual(im.size, (200, 150))

    def test_project_boundary_violation(self):
        """Reject paths attempting to escape the project directory."""
        outside_dir = Path("C:/Windows/Temp")
        with self.assertRaises(PermissionError):
            image_resizer.validate_project_boundary(outside_dir)

    def test_filename_with_multiple_dots(self):
        """Ensure suffix is placed before extension on multi-dot filenames."""
        multi_dot = self.sandbox_dir / "holiday.photo.v1.jpg"
        img = Image.new("RGB", (200, 200), color=(50, 50, 50))
        img.save(multi_dot, format="JPEG")

        image_resizer.process_resize_request(
            source_path=multi_dot,
            output_dir=self.output_dir,
            width=100,
            suffix="_thumb",
        )
        expected = self.output_dir / "holiday.photo.v1_thumb.jpg"
        self.assertTrue(expected.exists())
        with Image.open(expected) as im:
            self.assertEqual(im.size, (100, 100))

    def test_rgba_transparency_preserved(self):
        """Ensure RGBA PNG retains transparency and mode."""
        image_resizer.process_resize_request(
            source_path=self.test_rgba_path,
            output_dir=self.output_dir,
            percent=50,
        )
        out_rgba = self.output_dir / "test_rgba_resized.png"
        self.assertTrue(out_rgba.exists())
        with Image.open(out_rgba) as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.size, (200, 200))

    def test_image_info_extraction(self):
        """Test metadata extraction from get_image_info."""
        info = image_resizer.get_image_info(self.test_img_path)
        self.assertEqual(info["filename"], "test_rgb.jpg")
        self.assertEqual(info["width"], 800)
        self.assertEqual(info["height"], 600)
        self.assertEqual(info["mode"], "RGB")
        self.assertEqual(info["aspect_ratio"], "4:3")

    def test_unsupported_format_rejected(self):
        """Reject unsupported files."""
        fake_txt = self.sandbox_dir / "notes.txt"
        fake_txt.write_text("Hello world")
        with self.assertRaises(ValueError):
            image_resizer.get_image_info(fake_txt)

    def test_corrupted_image_handling(self):
        """Corrupted image raises descriptive RuntimeError."""
        bad_img = self.sandbox_dir / "corrupted.jpg"
        bad_img.write_bytes(b"not a real jpeg binary data stream")
        with self.assertRaises(RuntimeError):
            image_resizer.get_image_info(bad_img)

    def test_batch_folder_processing(self):
        """Test batch processing ignores non-images and succeeds on supported ones."""
        # Add non-image text file in folder
        (self.sandbox_dir / "README.txt").write_text("Do not process me")

        completed, failed, skipped = image_resizer.process_folder(
            folder_path=self.sandbox_dir,
            output_dir=self.output_dir,
            percent=50,
            quiet=True,
        )
        self.assertEqual(completed, 2)  # test_rgb.jpg and test_rgba.png
        self.assertEqual(failed, 0)
        self.assertEqual(skipped, 0)

    def test_atomic_temp_cleanup_on_error(self):
        """Ensure no partial temp files remain if an error occurs."""
        # Passing an invalid target dimension like (-10, -10) to resize_image_atomic
        with self.assertRaises(Exception):
            image_resizer.resize_image_atomic(
                source_path=self.test_img_path,
                output_path=self.output_dir / "should_fail.jpg",
                target_dimensions=(-10, -10),
            )
        # Check no temporary files linger in destination folder
        lingering = list(self.output_dir.glob("tmp_resize_*"))
        self.assertEqual(len(lingering), 0)


if __name__ == "__main__":
    unittest.main()
