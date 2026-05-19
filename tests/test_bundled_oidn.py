"""Tests for bundled OIDN runtime resolution."""

import pytest
from pathlib import Path

from h_denoise_utils.core.config import AOVConfig
from h_denoise_utils.core.config import DenoiseConfig
from h_denoise_utils.core.denoiser import Denoiser
from h_denoise_utils.discovery import bundled_oidn


def _write_oidn_runtime(tmp_path):
    root = (
        tmp_path
        / "vendor"
        / "oidn-denoiser"
        / "windows-x64"
        / "oidn-{}".format(bundled_oidn.PINNED_OIDN_VERSION)
    )
    exe = root / "Denoiser.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("placeholder")
    return root, exe


def test_resolve_uses_env_override(monkeypatch, tmp_path):
    exe = tmp_path / "Denoiser.exe"
    exe.write_text("placeholder")
    monkeypatch.setenv(bundled_oidn.ENV_OIDN_DENOISER_EXE, str(exe))

    assert bundled_oidn.resolve_bundled_oidn_denoiser() == str(exe)


def test_resolve_uses_root_override(monkeypatch, tmp_path):
    root, exe = _write_oidn_runtime(tmp_path)
    monkeypatch.delenv(bundled_oidn.ENV_OIDN_DENOISER_EXE, raising=False)
    monkeypatch.setenv(bundled_oidn.ENV_OIDN_ROOT, str(root))

    assert bundled_oidn.resolve_bundled_oidn_denoiser() == str(exe)


def test_resolve_uses_bundled_runtime(monkeypatch, tmp_path):
    monkeypatch.delenv(bundled_oidn.ENV_OIDN_DENOISER_EXE, raising=False)
    monkeypatch.delenv(bundled_oidn.ENV_OIDN_ROOT, raising=False)
    monkeypatch.setattr(bundled_oidn, "_package_root", lambda: tmp_path)
    _root, exe = _write_oidn_runtime(tmp_path)

    assert bundled_oidn.resolve_bundled_oidn_denoiser() == str(exe)


def test_legacy_resolver_alias_uses_custom_wrapper(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled_oidn, "_package_root", lambda: tmp_path)
    _root, exe = _write_oidn_runtime(tmp_path)

    assert bundled_oidn.resolve_bundled_oidn_denoise() == str(exe)


def test_available_bundled_oidn_runtimes(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled_oidn, "_package_root", lambda: tmp_path)
    _root, exe = _write_oidn_runtime(tmp_path)

    assert bundled_oidn.available_bundled_oidn_runtimes() == {"windows-x64": exe}


def test_resolve_missing_optional_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv(bundled_oidn.ENV_OIDN_DENOISER_EXE, raising=False)
    monkeypatch.delenv(bundled_oidn.ENV_OIDN_ROOT, raising=False)
    monkeypatch.setattr(bundled_oidn, "_package_root", lambda: tmp_path)

    assert bundled_oidn.resolve_bundled_oidn_denoiser(required=False) is None


def test_invalid_platform_raises():
    with pytest.raises(ValueError, match="Unsupported OIDN runtime platform"):
        bundled_oidn.resolve_bundled_oidn_denoiser(
            required=False,
            platform="linux-x64",
        )


def test_denoiser_oidn_backend_prepares_when_wrapper_exists(tmp_path):
    exe = tmp_path / "Denoiser.exe"
    exe.write_text("placeholder")
    input_file = tmp_path / "input.exr"
    input_file.write_bytes(b"not an exr, but enough for prepare path tests")

    denoiser = Denoiser(
        input_path=str(input_file),
        denoise_config=DenoiseConfig(backend="oidn"),
        denoiser_path=str(exe),
    )
    try:
        result = denoiser.prepare()
        assert result["status"] == "ready"
    finally:
        denoiser.cleanup()


def test_denoiser_oidn_backend_runs_optix_compatible_command(monkeypatch, tmp_path):
    exe = tmp_path / "Denoiser.exe"
    exe.write_text("placeholder")
    input_file = tmp_path / "input.exr"
    input_file.write_bytes(b"not an exr, but enough for command path tests")
    output_dir = tmp_path / "out"
    captured = {}

    def fake_run_subprocess(cmd, timeout=300):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        output_path = cmd[cmd.index("-o") + 1]
        with open(output_path, "wb") as stream:
            stream.write(b"denoised")
        return True, ""

    monkeypatch.setattr("h_denoise_utils.core.denoiser.run_subprocess", fake_run_subprocess)

    denoiser = Denoiser(
        input_path=str(input_file),
        denoise_config=DenoiseConfig(backend="oidn", overwrite=True),
        aov_config=AOVConfig(
            beauty_plane="C",
            albedo_plane="albedo",
            normal_plane="N",
            aovs_to_denoise=["directdiffuse", "indirectdiffuse"],
        ),
        denoiser_path=str(exe),
        output_folder=str(output_dir),
    )

    try:
        assert denoiser.prepare()["status"] == "ready"
        result = denoiser.denoise_one(0)
    finally:
        denoiser.cleanup()

    assert result["status"] == "success"
    assert captured["timeout"] == 300
    cmd = captured["cmd"]
    assert cmd[0] == str(exe)
    assert cmd[1:4] == ["-v", "1", "-multipart"]
    assert Path(cmd[4]).name == "input.exr"
    assert Path(cmd[4]).parent.name == "in"
    assert cmd[5] == "-o"
    assert Path(cmd[6]).name == "den_input.exr"
    assert Path(cmd[6]).parent.name == "out"
    assert "-beauty-name" in cmd
    assert cmd[cmd.index("-beauty-name") + 1] == "C"
    assert cmd[cmd.index("-albedo-name") + 1] == "albedo"
    assert cmd[cmd.index("-normal-name") + 1] == "N"
    assert cmd[cmd.index("-aov-name0") + 1] == "directdiffuse"
    assert cmd[cmd.index("-aov-name1") + 1] == "indirectdiffuse"
