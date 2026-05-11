"""Tests for AOV inspection helpers."""

from h_denoise_utils.ui.services import aov_inspector


def test_find_first_exr_from_selected_files(tmp_path):
    exr_path = tmp_path / "frame.exr"
    exr_path.write_text("data")
    result = aov_inspector.find_first_exr("ignored", [str(exr_path)])
    assert result == str(exr_path)


def test_analyze_aovs_no_exr(tmp_path):
    result = aov_inspector.analyze_aovs(str(tmp_path))
    assert result["status"] == "no_exr"
    assert result["exr_file"] is None


def test_analyze_aovs_no_planes(monkeypatch, tmp_path):
    exr_path = tmp_path / "frame.exr"
    exr_path.write_text("data")

    def fake_list_exr_planes(_path, oiiotool_path=None):
        return []

    monkeypatch.setattr(aov_inspector, "list_exr_planes", fake_list_exr_planes)
    result = aov_inspector.analyze_aovs(str(exr_path))
    assert result["status"] == "no_planes"
    assert result["exr_file"] == str(exr_path)


def test_analyze_aovs_error(monkeypatch, tmp_path):
    exr_path = tmp_path / "frame.exr"
    exr_path.write_text("data")

    def fake_list_exr_planes(_path, oiiotool_path=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(aov_inspector, "list_exr_planes", fake_list_exr_planes)
    result = aov_inspector.analyze_aovs(str(exr_path))
    assert result["status"] == "error"
    assert "boom" in result["error"]


def test_analyze_aovs_ok(monkeypatch, tmp_path):
    exr_path = tmp_path / "frame.exr"
    exr_path.write_text("data")

    def fake_list_exr_planes(_path, oiiotool_path=None):
        return ["C", "N"]

    monkeypatch.setattr(aov_inspector, "list_exr_planes", fake_list_exr_planes)
    result = aov_inspector.analyze_aovs(str(exr_path))
    assert result["status"] == "ok"
    assert result["planes"] == ["C", "N"]
    assert result["exr_file"] == str(exr_path)
