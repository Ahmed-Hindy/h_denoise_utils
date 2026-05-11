"""Tests for output path helpers."""

import os

from h_denoise_utils.ui.services import output_paths


def test_preview_output_path_for_directory(tmp_path):
    result = output_paths.preview_output_path(str(tmp_path), "")
    assert result.endswith(os.path.join(str(tmp_path), "denoised"))


def test_preview_output_path_for_file(tmp_path):
    file_path = tmp_path / "frame.exr"
    file_path.write_text("data")
    result = output_paths.preview_output_path(str(file_path), "")
    assert result.endswith(os.path.join(str(tmp_path), "denoised"))


def test_preview_output_path_empty():
    assert output_paths.preview_output_path("", "") == ""
