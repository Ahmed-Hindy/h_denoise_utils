"""Recent paths persistence helpers."""

from __future__ import annotations

import os


def load_recent_paths(settings: object) -> list[str]:
    """Load the list of recently opened directory paths from settings.

    Args:
        settings: The QSettings object or equivalent settings manager.

    Returns:
        List[str]: A list of normalized recent path strings.
    """
    value = settings.value("recent_paths", [])
    if isinstance(value, str):
        paths = [value]
    elif isinstance(value, (list, tuple)):
        paths = list(value)
    else:
        paths = []
    return [os.path.normpath(p) for p in paths if p]


def save_recent_paths(settings: object, paths: list[str]) -> None:
    """Save the list of recently opened directory paths to settings.

    Args:
        settings: The QSettings object or equivalent settings manager.
        paths: A list of path strings to save.
    """
    settings.setValue("recent_paths", list(paths))


def remember_path(paths: list[str], path: str, max_items: int = 10) -> list[str]:
    """Add a new path to the list of recent paths, maintaining constraints.

    Deduplicates the path, validates it exists, and limits the list size.

    Args:
        paths: Current list of path strings.
        path: The new path to add/promote.
        max_items: Maximum number of items allowed in the list.

    Returns:
        List[str]: Updated list of normalized path strings.
    """
    if not path:
        return list(paths)
    norm = os.path.normpath(path)
    if not os.path.exists(norm):
        return list(paths)
    new_paths = [p for p in paths if p != norm]
    new_paths.insert(0, norm)
    return new_paths[:max_items]
