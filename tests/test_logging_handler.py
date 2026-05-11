"""Tests for QtLogHandler."""

import logging

from h_denoise_utils.ui.logging_handler import QtLogHandler


def test_qt_log_handler_emits_signal(qtbot):
    records = []
    handler = QtLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.new_record.connect(lambda msg, level: records.append((msg, level)))

    logger = logging.getLogger("h_denoise_utils.tests.logging_handler")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    old_level = logger.level
    logger.handlers = []
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        logger.info("Hello")
    finally:
        logger.handlers = old_handlers
        logger.propagate = old_propagate
        logger.setLevel(old_level)

    assert records == [("Hello", "info")]
