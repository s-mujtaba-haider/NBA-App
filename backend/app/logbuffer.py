"""Keeps recent log records in memory (for /api/logs) and warnings+ in the database."""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

_buffer: Deque[Dict[str, Any]] = deque(maxlen=5000)
_lock = threading.Lock()


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                     "level": record.levelname, "source": record.name, "message": record.getMessage()}
            with _lock:
                _buffer.append(entry)
            if record.levelno >= logging.WARNING and not record.name.startswith("sqlalchemy"):
                from .db import LogEntry, session_scope
                with session_scope() as s:
                    s.add(LogEntry(level=record.levelname, source=record.name[:60], message=entry["message"][:4000]))
        except Exception:
            pass


def install(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not any(isinstance(h, BufferHandler) for h in root.handlers):
        h = BufferHandler(level=level)
        root.addHandler(h)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, BufferHandler) for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
        root.addHandler(sh)
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def recent(level: str = "all", limit: int = 100, source: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    min_level = levels.get(level.upper(), 0) if level and level.lower() != "all" else 0
    with _lock:
        items = list(_buffer)
    out = [e for e in reversed(items) if levels.get(e["level"], 0) >= min_level
           and (not source or source.lower() in e["source"].lower())
           and (not search or search.lower() in e["message"].lower())]
    return out[:limit]
