"""Tests for core.config module."""

import pytest
from h_denoise_utils.core.config import (
    AOVConfig,
    DenoiseConfig,
    normalize_plane_name,
    is_beauty_plane,
    DEFAULT_INPUT_EXTS,
    AOVS_NEVER_DENOISE,
    BEAUTY_AOV_ALIASES,
)


class TestNormalizePlaneName:
    """Tests for normalize_plane_name function."""

    def test_none_returns_empty_string(self):
        """Test that None input returns empty string."""
        assert normalize_plane_name(None) == ""

    def test_lowercase_conversion(self):
        """Test that uppercase is converted to lowercase."""
        assert normalize_plane_name("NORMAL") == "normal"
        assert normalize_plane_name("Albedo") == "albedo"

    def test_strip_whitespace(self):
        """Test that whitespace is stripped."""
        assert normalize_plane_name("  normal  ") == "normal"
        assert normalize_plane_name("\talbedo\n") == "albedo"


class TestAOVConfig:
    """Tests for AOVConfig dataclass."""

    def test_default_values(self):
        """Test default initialization."""
        config = AOVConfig()
        assert config.normal_plane is None
        assert config.albedo_plane is None
        assert config.motionvectors_plane is None
        assert config.aovs_to_denoise is None
        assert config.extra_aovs is None

    def test_custom_values(self):
        """Test initialization with custom values."""
        config = AOVConfig(
            normal_plane="N",
            albedo_plane="albedo",
            aovs_to_denoise=["diffuse", "specular"],
        )
        assert config.normal_plane == "N"
        assert config.albedo_plane == "albedo"
        assert config.aovs_to_denoise == ["diffuse", "specular"]

    def test_immutable(self):
        """Test that dataclass is frozen (immutable)."""
        config = AOVConfig(normal_plane="N")
        with pytest.raises(AttributeError):
            config.normal_plane = "normal"


class TestDenoiseConfig:
    """Tests for DenoiseConfig dataclass."""

    def test_default_values(self):
        """Test default initialization."""
        config = DenoiseConfig()
        assert config.backend == "optix"
        assert config.temporal is False
        assert config.overwrite is False
        assert config.prefix == "den_"

    def test_valid_backends(self):
        """Test that valid backends are accepted."""
        config1 = DenoiseConfig(backend="optix")
        config2 = DenoiseConfig(backend="oidn")
        assert config1.backend == "optix"
        assert config2.backend == "oidn"

    def test_invalid_backend_raises_error(self):
        """Test that invalid backend raises ValueError."""
        with pytest.raises(ValueError, match="Invalid backend"):
            DenoiseConfig(backend="invalid")

    def test_valid_exrmode_values(self):
        """Test that valid exrmode values are accepted."""
        config1 = DenoiseConfig(exrmode=-1)
        config2 = DenoiseConfig(exrmode=0)
        config3 = DenoiseConfig(exrmode=1)
        assert config1.exrmode == -1
        assert config2.exrmode == 0
        assert config3.exrmode == 1

    def test_invalid_exrmode_raises_error(self):
        """Test that invalid exrmode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid exrmode"):
            DenoiseConfig(exrmode=2)

    def test_invalid_threads_raises_error(self):
        """Test that invalid thread count raises ValueError."""
        with pytest.raises(ValueError, match="Invalid threads"):
            DenoiseConfig(threads=0)
        with pytest.raises(ValueError, match="Invalid threads"):
            DenoiseConfig(threads=-1)

    def test_immutable(self):
        """Test that dataclass is frozen (immutable)."""
        config = DenoiseConfig()
        with pytest.raises(AttributeError):
            config.backend = "oidn"


class TestConstants:
    """Tests for module constants."""

    def test_default_input_exts_contains_exr(self):
        """Test that DEFAULT_INPUT_EXTS includes .exr."""
        assert ".exr" in DEFAULT_INPUT_EXTS

    def test_aovs_never_denoise_contains_normal(self):
        """Test that AOVS_NEVER_DENOISE includes normal."""
        assert "normal" in AOVS_NEVER_DENOISE
        assert "albedo" in AOVS_NEVER_DENOISE

    def test_beauty_aliases_contains_common_names(self):
        """Test that BEAUTY_AOV_ALIASES includes common names."""
        assert "c" in BEAUTY_AOV_ALIASES
        assert "rgba" in BEAUTY_AOV_ALIASES
        assert "beauty" in BEAUTY_AOV_ALIASES


class TestIsBeautyPlane:
    """Tests for is_beauty_plane helper."""

    def test_detects_common_aliases(self):
        assert is_beauty_plane("C")
        assert is_beauty_plane("RGBA")
        assert is_beauty_plane("beauty")
        assert is_beauty_plane("Ci")

    def test_ignores_non_beauty_planes(self):
        assert not is_beauty_plane("diffuse")
        assert not is_beauty_plane("specular")
