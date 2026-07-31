"""Structural tests for the Nuke OptiX and OIDN playground."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYGROUND = REPO_ROOT / "examples" / "nuke-denoise-playground"


def test_playground_files_exist_and_python_parses() -> None:
    """Keep the user-facing launcher, Nuke script, and helper together."""
    expected = {
        PLAYGROUND / "README.md",
        PLAYGROUND / "hdu-denoise-playground.nk",
        PLAYGROUND / "launch-nuke-playground.ps1",
        PLAYGROUND / "hdu_playground.py",
    }
    assert all(path.is_file() for path in expected)
    ast.parse((PLAYGROUND / "hdu_playground.py").read_text(encoding="utf-8"))


def test_nuke_script_bootstraps_the_generated_graph() -> None:
    """Open the same dynamic comparison graph in all supported Nuke versions."""
    script = (PLAYGROUND / "hdu-denoise-playground.nk").read_text(encoding="utf-8")
    assert "version 14.1 v8" in script
    assert "import hdu_playground; hdu_playground.configure()" in script
    assert "launch-nuke-playground.ps1" in script


def test_launcher_selects_matching_native_runtimes_without_downloading() -> None:
    """Use existing validated bundles and avoid hidden network work at launch."""
    launcher = (PLAYGROUND / "launch-nuke-playground.ps1").read_text(
        encoding="utf-8"
    )
    for version in ("14.1v8", "15.0v1", "15.1v4", "17.0v3"):
        assert version in launcher
    for version in ("8.1", "9.0", "9.1"):
        assert f'"{version}"' in launcher
    assert "build\\nuke-optix-package\\nuke-$Version\\optix-$Optix" in launcher
    assert "oidn-2.5.0\\Denoiser.exe" in launcher
    assert launcher.index("oidn-2.5.0") < launcher.index("oidn-2.4.1")
    assert "$env:NUKE_PATH" in launcher
    assert "$env:HDU_PLAYGROUND_INPUT" in launcher
    assert "$env:HDU_PLAYGROUND_OIDN_OUTPUT" in launcher
    assert "Remove-Item -Path Env:CUDA_CACHE_MAXSIZE" in launcher
    assert "$PrepareOnly" in launcher
    assert "Invoke-WebRequest" not in launcher
    assert "curl" not in launcher.lower()


def test_helper_builds_comparison_and_write_branches() -> None:
    """Expose source, OptiX variants, OIDN, differences, and render outputs."""
    helper = (PLAYGROUND / "hdu_playground.py").read_text(encoding="utf-8")
    expected_nodes = {
        "HDU_SOURCE_MULTIPART",
        "HDU_BEAUTY",
        "HDU_ALBEDO",
        "HDU_NORMAL",
        "HDU_OPTIX_BEAUTY",
        "HDU_OPTIX_ALBEDO",
        "HDU_OPTIX_GUIDED",
        "HDU_OIDN_MULTIPART",
        "HDU_OIDN_BEAUTY",
        "HDU_OPTIX_OIDN_DIFFERENCE",
        "HDU_DIFFERENCE_X20",
        "HDU_WRITE_OPTIX_BEAUTY",
        "HDU_WRITE_OPTIX_GUIDED",
        "HDU_WRITE_OPTIX_OIDN_DIFFERENCE",
        "HDU_PLAYGROUND_CONTROLS",
        "HDU_PLAYGROUND_VIEWER",
    }
    assert all(name in helper for name in expected_nodes)
    assert '"HOptixDenoise"' in helper
    assert '"-multipart"' in helper
    assert '"-beauty-name"' in helper
    assert '"-albedo-name"' in helper
    assert '"-normal-name"' in helper
    assert "_enumeration_index" in helper
    assert "_validate_write_output" in helper
    assert "nuke.execute(node, 1, 1)" in helper
