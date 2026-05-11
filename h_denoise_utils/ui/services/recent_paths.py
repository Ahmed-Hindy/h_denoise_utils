"""Recent paths persistence helpers."""

import os


def load_recent_paths(settings):
    # type: (object) -> List[str]
    value = settings.value("recent_paths", [])
    if isinstance(value, str):
        paths = [value]
    elif isinstance(value, (list, tuple)):
        paths = list(value)
    else:
        paths = []
    return [os.path.normpath(p) for p in paths if p]


def save_recent_paths(settings, paths):
    # type: (object, List[str]) -> None
    settings.setValue("recent_paths", list(paths))


def remember_path(paths, path, max_items=10):
    # type: (List[str], str, int) -> List[str]
    if not path:
        return list(paths)
    norm = os.path.normpath(path)
    if not os.path.exists(norm):
        return list(paths)
    new_paths = [p for p in paths if p != norm]
    new_paths.insert(0, norm)
    return new_paths[:max_items]
