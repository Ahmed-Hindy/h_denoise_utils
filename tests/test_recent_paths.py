"""Tests for recent paths helpers."""

import os

from h_denoise_utils.ui.services import recent_paths


class _DummySettings(object):
    def __init__(self, value=None):
        self._value = value
        self.saved = None

    def value(self, _key, default=None):
        return self._value if self._value is not None else default

    def setValue(self, _key, value):
        self.saved = value


def test_load_recent_paths_string(tmp_path):
    path = tmp_path / "A"
    path.mkdir()
    settings = _DummySettings(str(path))
    result = recent_paths.load_recent_paths(settings)
    assert result == [os.path.normpath(str(path))]


def test_load_recent_paths_list(tmp_path):
    path_a = tmp_path / "A"
    path_b = tmp_path / "B"
    path_a.mkdir()
    path_b.mkdir()
    settings = _DummySettings([str(path_a), str(path_b)])
    result = recent_paths.load_recent_paths(settings)
    assert result == [
        os.path.normpath(str(path_a)),
        os.path.normpath(str(path_b)),
    ]


def test_remember_path_dedupes_and_orders(tmp_path):
    path_a = tmp_path / "A"
    path_b = tmp_path / "B"
    path_a.mkdir()
    path_b.mkdir()
    paths = [os.path.normpath(str(path_a)), os.path.normpath(str(path_b))]
    updated = recent_paths.remember_path(paths, str(path_a), max_items=10)
    assert updated[0] == os.path.normpath(str(path_a))
    assert updated[1] == os.path.normpath(str(path_b))


def test_remember_path_ignores_missing(tmp_path):
    missing = tmp_path / "missing"
    paths = []
    updated = recent_paths.remember_path(paths, str(missing), max_items=10)
    assert updated == []


def test_save_recent_paths(tmp_path):
    path = tmp_path / "A"
    path.mkdir()
    settings = _DummySettings()
    recent_paths.save_recent_paths(settings, [str(path)])
    assert settings.saved == [str(path)]
