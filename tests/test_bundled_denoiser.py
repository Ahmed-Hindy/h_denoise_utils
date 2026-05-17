"""Tests for bundled denoiser resolution."""

from h_denoise_utils.discovery import bundled_denoiser


def test_resolve_uses_env_override(monkeypatch, tmp_path):
    exe = tmp_path / "Denoiser.exe"
    exe.write_text("placeholder")
    monkeypatch.setenv(bundled_denoiser.ENV_DENOISER_EXE, str(exe))

    assert bundled_denoiser.resolve_bundled_denoiser() == str(exe)


def test_resolve_missing_optional_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv(bundled_denoiser.ENV_DENOISER_EXE, raising=False)
    monkeypatch.setattr(
        bundled_denoiser,
        "bundled_denoiser_path",
        lambda: tmp_path / "missing" / "Denoiser.exe",
    )

    assert bundled_denoiser.resolve_bundled_denoiser(required=False) is None


def test_resolve_missing_env_override_raises(monkeypatch, tmp_path):
    missing = tmp_path / "missing.exe"
    monkeypatch.setenv(bundled_denoiser.ENV_DENOISER_EXE, str(missing))

    try:
        bundled_denoiser.resolve_bundled_denoiser()
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")
