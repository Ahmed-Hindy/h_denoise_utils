"""Tests for core.command_builder module."""

from h_denoise_utils.core.command_builder import (
    build_bundled_multipart_command,
    build_bundled_optix_command,
    build_oidn_denoise_command,
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


class TestBuildBundledMultipartCommand:
    """Tests for the shared OptiX/OIDN Denoiser.exe CLI contract."""

    def test_oidn_uses_optix_compatible_multipart_command(self):
        cmd = build_bundled_multipart_command(
            denoiser_exe="/oidn/Denoiser.exe",
            input_path="/in.exr",
            output_path="/out.exr",
            beauty_plane="C",
            albedo_plane="albedo",
            normal_plane="N",
            aovs_to_denoise=["directdiffuse", "indirectdiffuse"],
        )
        assert cmd == [
            "/oidn/Denoiser.exe",
            "-v",
            "1",
            "-multipart",
            "/in.exr",
            "-o",
            "/out.exr",
            "-beauty-name",
            "C",
            "-albedo-name",
            "albedo",
            "-normal-name",
            "N",
            "-aov-name0",
            "directdiffuse",
            "-aov-name1",
            "indirectdiffuse",
        ]


class TestBuildOidnDenoiseCommand:
    """Tests for stock oidnDenoise command construction."""

    def test_minimal_hdr_command(self):
        cmd = build_oidn_denoise_command(
            denoiser_exe="/oidnDenoise.exe",
            input_path="/input.pfm",
            output_path="/output.pfm",
        )
        assert cmd == [
            "/oidnDenoise.exe",
            "--hdr",
            "/input.pfm",
            "-o",
            "/output.pfm",
            "-v",
            "1",
        ]

    def test_guides_device_quality_and_threads(self):
        cmd = build_oidn_denoise_command(
            denoiser_exe="/oidnDenoise.exe",
            input_path="/color.pfm",
            output_path="/denoised.pfm",
            albedo_path="/albedo.pfm",
            normal_path="/normal.pfm",
            device="cpu",
            quality="balanced",
            threads=8,
            verbosity=3,
        )
        assert cmd == [
            "/oidnDenoise.exe",
            "--device",
            "cpu",
            "--hdr",
            "/color.pfm",
            "--alb",
            "/albedo.pfm",
            "--nrm",
            "/normal.pfm",
            "--quality",
            "balanced",
            "--threads",
            "8",
            "-o",
            "/denoised.pfm",
            "-v",
            "3",
        ]
