"""Tests for subprocess execution utilities."""

from types import SimpleNamespace

from h_denoise_utils.utils import process_utils


def test_run_subprocess_passes_environment(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(process_utils.subprocess, "run", fake_run)

    environment = {"LD_LIBRARY_PATH": "/runtime"}
    success, error = process_utils.run_subprocess(
        ["Denoiser", "input.exr"],
        timeout=42,
        env=environment,
    )

    assert success is True
    assert error == ""
    assert captured["cmd"] == ["Denoiser", "input.exr"]
    assert captured["kwargs"]["timeout"] == 42
    assert captured["kwargs"]["env"] == environment
