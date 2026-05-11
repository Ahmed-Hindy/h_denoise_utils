"""Tests for utils.file_utils module."""

import os
from h_denoise_utils.utils.file_utils import (
    natural_sort_key,
    is_image_file,
    scan_images,
    build_output_path,
    compute_output_folder,
)


class TestNaturalSortKey:
    """Tests for natural_sort_key function."""

    def test_numeric_sorting(self):
        """Test that numbers are sorted naturally."""
        names = ["file10.exr", "file2.exr", "file1.exr"]
        sorted_names = sorted(names, key=natural_sort_key)
        assert sorted_names == ["file1.exr", "file2.exr", "file10.exr"]

    def test_mixed_content(self):
        """Test sorting with mixed alphanumeric content."""
        names = ["a10b5", "a2b10", "a2b2"]
        sorted_names = sorted(names, key=natural_sort_key)
        assert sorted_names == ["a2b2", "a2b10", "a10b5"]


class TestIsImageFile:
    """Tests for is_image_file function."""

    def test_exr_file(self):
        """Test that .exr files are recognized."""
        assert is_image_file("render.exr", [".exr", ".png"])

    def test_case_insensitive(self):
        """Test case-insensitive extension matching."""
        assert is_image_file("RENDER.EXR", [".exr"])

    def test_non_image_file(self):
        """Test that non-image files are rejected."""
        assert not is_image_file("data.txt", [".exr", ".png"])


class TestScanImages:
    """Tests for scan_images function."""

    def test_scan_empty_folder(self, tmp_path):
        """Test scanning empty folder returns empty list."""
        result = scan_images(str(tmp_path), [".exr"])
        assert result == []

    def test_scan_with_images(self, tmp_path):
        """Test scanning folder with image files."""
        # Create test files
        (tmp_path / "render.exr").touch()
        (tmp_path / "data.txt").touch()
        (tmp_path / "image.png").touch()

        result = scan_images(str(tmp_path), [".exr", ".png"])
        assert len(result) == 2
        assert "render.exr" in result
        assert "image.png" in result
        assert "data.txt" not in result


class TestBuildOutputPath:
    """Tests for build_output_path function."""

    def test_basic_output_path(self, tmp_path):
        """Test building output path with prefix."""
        src = str(tmp_path / "render.exr")
        out_folder = str(tmp_path / "output")
        os.makedirs(out_folder)

        result = build_output_path(src, out_folder, "den_")
        expected = os.path.join(out_folder, "den_render.exr")
        assert os.path.normpath(result) == os.path.normpath(expected)

    def test_path_traversal_protection(self, tmp_path):
        """Test that path traversal is prevented."""
        # Create a subdirectory
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        out_folder = str(sub_dir)

        # Try to escape using parent directory reference
        # This should be caught by normpath validation
        src = str(tmp_path / "render.exr")

        # Test with a malicious prefix that tries to escape
        try:
            result = build_output_path(src, out_folder, "../../../evil_")
            # If we get here, check that result is still within out_folder
            out_folder_abs = os.path.normcase(os.path.abspath(out_folder))
            result_abs = os.path.normcase(os.path.abspath(result))
            assert os.path.commonpath([result_abs, out_folder_abs]) == out_folder_abs
        except ValueError:
            # This is also acceptable - the function rejected the attempt
            pass


class TestComputeOutputFolder:
    """Tests for compute_output_folder function."""

    def test_folder_input(self, tmp_path):
        """Test computing output folder from folder input."""
        result = compute_output_folder(str(tmp_path), [".exr"])
        expected = os.path.join(str(tmp_path), "denoised").replace("\\", "/")
        assert result == expected
        assert os.path.exists(result)

    def test_file_input(self, tmp_path):
        """Test computing output folder from file input."""
        test_file = tmp_path / "render.exr"
        test_file.touch()

        result = compute_output_folder(str(test_file), [".exr"])
        expected = os.path.join(str(tmp_path), "denoised").replace("\\", "/")
        assert result == expected
