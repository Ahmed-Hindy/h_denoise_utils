"""Tests for core.command_builder module."""

import pytest
from h_denoise_utils.core.command_builder import (
    build_idenoise_command,
    override_normal_plane,
)


class TestBuildIdenoiseCommand:
    """Tests for build_idenoise_command function."""

    def test_minimal_command(self):
        """Test building command with minimal arguments."""
        cmd = build_idenoise_command(
            idenoise_exe="/path/to/idenoise",
            input_path="/input.exr",
            output_path="/output.exr",
            backend="optix",
        )
        assert cmd == ["/path/to/idenoise", "/input.exr", "/output.exr", "-d", "optix"]

    def test_full_command(self):
        """Test building command with all arguments."""
        cmd = build_idenoise_command(
            idenoise_exe="/path/to/idenoise",
            input_path="/input.exr",
            output_path="/output.exr",
            backend="optix",
            normal_plane="N",
            albedo_plane="albedo",
            motionvectors_plane="velocity",
            prev_frame="/prev.exr",
            aovs_to_denoise=["diffuse", "specular"],
            extra_aovs=["Z"],
            exrmode=1,
            options_json='{"blendfactor": 0.5}',
        )

        expected = [
            "/path/to/idenoise",
            "/input.exr",
            "/output.exr",
            "-d",
            "optix",
            "-n",
            "N",
            "-a",
            "albedo",
            "-m",
            "velocity",
            "-p",
            "/prev.exr",
            "--aovs",
            "diffuse",
            "specular",
            "--extra_aovs",
            "Z",
            "--exrmode",
            "1",
            "--options",
            '{"blendfactor": 0.5}',
        ]
        assert cmd == expected

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON in options raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            build_idenoise_command(
                idenoise_exe="/path/to/idenoise",
                input_path="/input.exr",
                output_path="/output.exr",
                backend="optix",
                options_json="{invalid json}",
            )

    def test_empty_aov_lists_ignored(self):
        """Test that empty AOV lists are not added to command."""
        cmd = build_idenoise_command(
            idenoise_exe="/path/to/idenoise",
            input_path="/input.exr",
            output_path="/output.exr",
            backend="oidn",
            aovs_to_denoise=[],
            extra_aovs=[],
        )
        assert "--aovs" not in cmd
        assert "--extra_aovs" not in cmd


class TestOverrideNormalPlane:
    """Tests for override_normal_plane function."""

    def test_replace_existing_normal(self):
        """Test replacing existing -n flag."""
        cmd = ["/idenoise", "in.exr", "out.exr", "-n", "normal", "-d", "optix"]
        result = override_normal_plane(cmd, "N")
        assert result == ["/idenoise", "in.exr", "out.exr", "-n", "N", "-d", "optix"]

    def test_add_normal_when_missing(self):
        """Test adding -n flag when it doesn't exist."""
        cmd = ["/idenoise", "in.exr", "out.exr", "-d", "optix"]
        result = override_normal_plane(cmd, "N")
        # Should insert before output path
        assert "-n" in result
        assert "N" in result
        # Output path should still be present
        assert "out.exr" in result

    def test_minimal_command_add_normal(self):
        """Test adding normal to minimal command."""
        cmd = ["/idenoise", "in.exr"]
        result = override_normal_plane(cmd, "N")
        assert "-n" in result
        assert "N" in result
