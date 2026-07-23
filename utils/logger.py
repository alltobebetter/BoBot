"""统一日志（控制台 + 可选文件）。"""
import logging
import os
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path("data/logs")


def _build() -> logging.Logger:
    logger = logging.getLogger("aibob")
    if logger.handlers:
        return logger
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logger.setLevel(level)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(ch)
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(_LOG_DIR / f"bot_{datetime.now():%Y%m%d}.log", encoding="utf-8")
        fh.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(fh)
    except Exception:
        pass
    return logger


class _Log:
    def __init__(self):
        self._l = _build()

    @staticmethod
    def _fmt(msg, kw):
        if kw:
            return f"{msg} | " + " | ".join(f"{k}={v}" for k, v in kw.items())
        return str(msg)

    def debug(self, msg, **kw):
        self._l.debug(self._fmt(msg, kw))

    def info(self, msg, **kw):
        self._l.info(self._fmt(msg, kw))

    def warning(self, msg, **kw):
        self._l.warning(self._fmt(msg, kw))

    def error(self, msg, exc=None, **kw):
        if exc is not None:
            self._l.error(f"{self._fmt(msg, kw)}: {exc}", exc_info=True)
        else:
            self._l.error(self._fmt(msg, kw))


log = _Log()
