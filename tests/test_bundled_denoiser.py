"""Tests for bundled denoiser resolution."""

import pytest

from h_denoise_utils.discovery import bundled_denoiser


def _write_variant(tmp_path, version):
    exe = (
        tmp_path
        / "vendor"
        / "optix-denoiser"
        / "windows-x64"
        / "optix-{}".format(version)
        / "Denoiser.exe"
    )
    exe.parent.mkdir(parents=True)
    exe.write_text("placeholder")
    return exe


def test_resolve_default_uses_optix_9(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled_denoiser, "_package_root", lambda: tmp_path)
    exe = _write_variant(tmp_path, "9.0")

    assert bundled_denoiser.resolve_bundled_denoiser() == str(exe)


def test_resolve_uses_selected_optix_version(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled_denoiser, "_package_root", lambda: tmp_path)
    exe = _write_variant(tmp_path, "8.1")

    assert bundled_denoiser.resolve_bundled_denoiser(optix_version="8.1") == str(exe)


def test_resolve_falls_back_when_default_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled_denoiser, "_package_root", lambda: tmp_path)
    exe = _write_variant(tmp_path, "8.1")

    assert bundled_denoiser.resolve_bundled_denoiser() == str(exe)


def test_resolve_invalid_optix_version_raises():
    with pytest.raises(ValueError, match="Unsupported OptiX runtime"):
        bundled_denoiser.resolve_bundled_denoiser(optix_version="7.0")


def test_resolve_missing_optional_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled_denoiser, "_package_root", lambda: tmp_path)

    assert bundled_denoiser.resolve_bundled_denoiser(required=False) is None


def test_available_bundled_denoisers(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled_denoiser, "_package_root", lambda: tmp_path)
    exe_8 = _write_variant(tmp_path, "8.1")
    exe_9 = _write_variant(tmp_path, "9.0")

    assert bundled_denoiser.available_bundled_denoisers() == {
        "8.1": exe_8,
        "9.0": exe_9,
    }
