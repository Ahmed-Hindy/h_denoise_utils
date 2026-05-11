"""Tests for h_denoise_utils.logger."""

import logging
import uuid

import pytest

from h_denoise_utils import logger as logger_module


def _reset_logger(name):
    # type: (str) -> None
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


def _flush_handlers(logger):
    # type: (logging.Logger) -> None
    for handler in logger.handlers:
        flush = getattr(handler, "flush", None)
        if flush is not None:
            flush()


@pytest.fixture
def logger_name():
    created = []

    def _make(prefix="logger_test"):
        # type: (str) -> str
        name = "{}_{}".format(prefix, uuid.uuid4().hex)
        created.append(name)
        return name

    yield _make

    for name in created:
        _reset_logger(name)


def test_setup_logger_returns_same_instance(logger_name, tmp_path):
    name = logger_name("standalone")

    logger_a = logger_module.setup_logger(name, log_dir=str(tmp_path))
    logger_b = logger_module.setup_logger(name, log_dir=str(tmp_path))

    assert logger_a is logger_b
    assert logger_a is logging.getLogger(name)
    assert len(logger_a.handlers) == 2


def test_setup_logger_uses_env_log_dir(monkeypatch, logger_name, tmp_path):
    monkeypatch.setenv("H_DENOISE_LOG_DIR", str(tmp_path))
    name = logger_name("envdir")

    logger = logger_module.setup_logger(name)
    logger.info("hello")
    _flush_handlers(logger)

    log_path = tmp_path / "{}.log".format(name)
    assert logger_module.get_log_dir() == str(tmp_path)
    assert log_path.exists()
    assert "hello" in log_path.read_text(encoding="utf-8")


def test_get_logger_matches_stdlib(logger_name):
    name = logger_name("compat")
    assert logger_module.get_logger(name) is logging.getLogger(name)


def test_package_child_logger_propagates_to_package_logger(tmp_path):
    package_name = "h_denoise_utils"
    child_name = "h_denoise_utils.tests.child"
    _reset_logger(package_name)
    _reset_logger(child_name)

    package_logger = logger_module.setup_logger(package_name, log_dir=str(tmp_path))
    records = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = _CaptureHandler()
    package_logger.addHandler(handler)
    try:
        child_logger = logging.getLogger(child_name)
        child_logger.info("from child")
    finally:
        package_logger.removeHandler(handler)
        handler.close()
        _reset_logger(child_name)
        _reset_logger(package_name)

    assert child_logger.handlers == []
    assert child_logger.propagate is True
    assert records == ["from child"]
