"""Tests for core.command_builder module."""

from h_denoise_utils.core.command_builder import (
    build_bundled_optix_command,
)


class TestBuildBundledOptixCommand:
    """Tests for bundled OptiX multipart command construction."""

    def test_minimal_multipart_command(self):
        cmd = build_bundled_optix_command(
            denoiser_exe="/path/to/Denoiser.exe",
            input_path="/input.exr",
            output_path="/output.exr",
        )
        assert cmd == [
            "/path/to/Denoiser.exe",
            "-v",
            "1",
            "-multipart",
            "/input.exr",
            "-o",
            "/output.exr",
            "-beauty-name",
            "C",
        ]

    def test_guides_and_aovs(self):
        cmd = build_bundled_optix_command(
            denoiser_exe="/Denoiser.exe",
            input_path="/in.exr",
            output_path="/out.exr",
            beauty_plane="beauty",
            albedo_plane="albedo",
            normal_plane="N",
            aovs_to_denoise=["directdiffuse", "indirectdiffuse"],
        )
        assert cmd == [
            "/Denoiser.exe",
            "-v",
            "1",
            "-multipart",
            "/in.exr",
            "-o",
            "/out.exr",
            "-beauty-name",
            "beauty",
            "-albedo-name",
            "albedo",
            "-normal-name",
            "N",
            "-aov-name0",
            "directdiffuse",
            "-aov-name1",
            "indirectdiffuse",
        ]
