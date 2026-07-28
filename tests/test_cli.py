"""Command-line entry point tests."""

import pytest

from h_denoise_utils import __main__ as main_module


class FakeDenoiser:
    """Small stand-in for the batch denoiser used by CLI tests."""

    def __init__(self, *, files=None, prep_status="ready", fail_index=None, **kwargs):
        """Capture constructor kwargs and configure fake run behavior.

        Args:
            files: Optional list of file names to expose.
            prep_status: Preparation status to return.
            fail_index: Optional index to fail during denoise_one.
            **kwargs: Constructor values passed by the CLI.
        """
        self.kwargs = kwargs
        self.files = list(files or ["input.exr"])
        self.prep_status = prep_status
        self.fail_index = fail_index
        self.cleaned = False
        self.calls = []

    def prepare(self):
        """Return a ready preparation result for the fake file list."""
        return {
            "status": self.prep_status,
            "file_count": len(self.files),
            "output_folder": self.kwargs.get("output_folder") or "out",
        }

    def denoise_one(self, index, prev_output=None):
        """Record a fake denoise operation."""
        self.calls.append((index, prev_output))
        if self.fail_index == index:
            return {"status": "error", "message": "boom"}
        return {
            "status": "success",
            "output_path": f"out/{self.files[index]}",
        }

    def cleanup(self):
        """Record cleanup."""
        self.cleaned = True


def test_cli_without_input_launches_gui(monkeypatch):
    """No input path preserves the existing GUI launch behavior."""
    launched = {}

    def fake_launch_gui(app_args=None):
        launched["app_args"] = app_args
        return "window"

    monkeypatch.setattr(main_module, "_launch_gui", fake_launch_gui)

    assert main_module.main([]) == "window"
    assert launched["app_args"] == ["h-denoise"]


def test_cli_backend_option_requires_input_path():
    """Denoise-only options should not be silently ignored by GUI launch."""
    with pytest.raises(SystemExit) as exc:
        main_module.main(["--backend", "oidn"])

    assert exc.value.code == 2


def test_cli_oidn_backend_builds_denoiser_config(monkeypatch, capsys):
    """The --backend oidn option is carried into DenoiseConfig."""
    created = {}

    def fake_resolve(backend, optix_version):
        created["runtime_request"] = (backend, optix_version)
        return "C:/runtimes/oidn/Denoiser.exe"

    def fake_create(**kwargs):
        fake = FakeDenoiser(files=["a.exr", "b.exr"], **kwargs)
        created["denoiser"] = fake
        return fake

    monkeypatch.setattr(main_module, "_resolve_cli_runtime", fake_resolve)
    monkeypatch.setattr(main_module, "_create_cli_denoiser", fake_create)

    result = main_module.main(
        [
            "G:/renders",
            "--backend",
            "oidn",
            "--normal-name",
            "N",
            "--albedo-name",
            "albedo",
            "--aov-name",
            "directdiffuse, indirectdiffuse",
            "--prefix",
            "oidn_",
            "--overwrite",
            "--output-folder",
            "G:/out",
        ]
    )

    fake = created["denoiser"]
    assert result == 0
    assert created["runtime_request"] == ("oidn", "9.0")
    assert fake.kwargs["backend"] == "oidn"
    assert fake.kwargs["denoiser_path"] == "C:/runtimes/oidn/Denoiser.exe"
    assert fake.kwargs["output_folder"] == "G:/out"
    assert fake.kwargs["overwrite"] is True
    assert fake.kwargs["prefix"] == "oidn_"
    assert fake.kwargs["beauty_plane"] == "C"
    assert fake.kwargs["normal_plane"] == "N"
    assert fake.kwargs["albedo_plane"] == "albedo"
    assert fake.kwargs["aovs_to_denoise"] == ["directdiffuse", "indirectdiffuse"]
    assert fake.calls == [(0, None), (1, "out/a.exr")]
    assert fake.cleaned is True
    assert "Using OIDN backend" in capsys.readouterr().out


def test_cli_optix_backend_uses_selected_runtime(monkeypatch):
    """The --optix-version option is used only when resolving OptiX."""
    created = {}

    def fake_resolve(backend, optix_version):
        created["runtime_request"] = (backend, optix_version)
        return "C:/runtimes/optix-9.1/Denoiser.exe"

    def fake_create(**kwargs):
        fake = FakeDenoiser(**kwargs)
        created["denoiser"] = fake
        return fake

    monkeypatch.setattr(main_module, "_resolve_cli_runtime", fake_resolve)
    monkeypatch.setattr(main_module, "_create_cli_denoiser", fake_create)

    result = main_module.main(
        [
            "G:/renders/input.exr",
            "--backend",
            "optix",
            "--optix-version",
            "9.1",
            "--beauty-name",
            "beauty",
        ]
    )

    assert result == 0
    assert created["runtime_request"] == ("optix", "9.1")
    assert created["denoiser"].kwargs["backend"] == "optix"
    assert created["denoiser"].kwargs["beauty_plane"] == "beauty"
    assert created["denoiser"].kwargs.get("output_folder") is None


def test_cli_missing_runtime_returns_error(monkeypatch, capsys):
    """Missing selected runtime reports an error and exits nonzero."""
    monkeypatch.setattr(
        main_module,
        "_resolve_cli_runtime",
        lambda backend, optix_version: None,
    )

    result = main_module.main(["G:/renders/input.exr", "--backend", "oidn"])

    assert result == 1
    assert "Bundled OIDN Denoiser.exe was not found" in capsys.readouterr().err


def test_cli_output_folder_is_optional_and_defaults_to_denoised(monkeypatch, tmp_path):
    """Omitting --output-folder defaults to a subfolder called 'denoised' next to input."""
    from pathlib import Path

    input_file = tmp_path / "image.exr"
    input_file.touch()

    fake_exe = tmp_path / "Denoiser.exe"
    fake_exe.touch()

    monkeypatch.setattr(
        main_module,
        "_resolve_cli_runtime",
        lambda backend, optix_version: str(fake_exe),
    )

    run_calls = []

    def fake_run_subprocess(cmd, timeout=300, env=None):
        run_calls.append(cmd)
        output_path = cmd[cmd.index("-o") + 1]
        Path(output_path).touch()
        return True, ""

    monkeypatch.setattr("h_denoise_utils.core.denoiser.run_subprocess", fake_run_subprocess)

    result = main_module.main([
        str(input_file),
        "--backend", "optix",
    ])

    assert result == 0
    expected_output_folder = tmp_path / "denoised"
    assert expected_output_folder.is_dir()
    assert (expected_output_folder / "den_image.exr").exists()
