import logging
import os
from logging.handlers import RotatingFileHandler

import logging_config


def _remove_climb_handlers():
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_climb_handler", False):
            root.removeHandler(h)
            h.close()


def test_configure_logging_creates_rotating_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    # Start clean so the idempotent guard doesn't skip setup from another test.
    _remove_climb_handlers()
    try:
        log_path = logging_config.configure_logging()

        assert log_path == os.path.join(str(tmp_path), "logs", "sidecar.log")
        assert os.path.exists(log_path)

        root = logging.getLogger()
        rotating = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler) and getattr(h, "_climb_handler", False)
        ]
        assert len(rotating) == 1

        # An emitted record actually lands in the file.
        logging.getLogger("test").warning("hello-logfile")
        for h in rotating:
            h.flush()
        with open(log_path, encoding="utf-8") as f:
            assert "hello-logfile" in f.read()
    finally:
        _remove_climb_handlers()


def test_configure_logging_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    _remove_climb_handlers()
    try:
        logging_config.configure_logging()
        logging_config.configure_logging()
        root = logging.getLogger()
        climb_handlers = [h for h in root.handlers if getattr(h, "_climb_handler", False)]
        # One file + one stream handler, not duplicated by the second call.
        assert len(climb_handlers) == 2
    finally:
        _remove_climb_handlers()
