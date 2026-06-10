"""Centralized logging for the sidecar.

`configure_logging()` is called once at startup (from `main.py`). It wires the
root logger to a rotating file under `<LOG_DIR>/logs/sidecar.log` *and* to stdout
so the Electron main process can still capture output into its own logfile. Every
module just uses `logging.getLogger(__name__)`; this is the only place handlers
are configured.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _resolve_log_dir() -> str:
    """Pick the directory that should hold the `logs/` folder.

    Electron injects `LOG_DIR` (the per-user data dir). Standalone backend dev
    has no such env, so fall back to the directory of `DB_PATH`, then cwd.
    """
    log_dir = os.environ.get("LOG_DIR")
    if not log_dir:
        db_path = os.environ.get("DB_PATH")
        log_dir = os.path.dirname(os.path.abspath(db_path)) if db_path else os.getcwd()
    return log_dir


def configure_logging() -> str:
    """Configure the root logger. Returns the logfile path (handy for tests)."""
    logs_dir = os.path.join(_resolve_log_dir(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "sidecar.log")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Idempotent: don't stack handlers if called twice (e.g. uvicorn reload).
    if any(getattr(h, "_climb_handler", False) for h in root.handlers):
        return log_path

    formatter = logging.Formatter(_FORMAT)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler._climb_handler = True  # type: ignore[attr-defined]

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler._climb_handler = True  # type: ignore[attr-defined]

    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    return log_path
