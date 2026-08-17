"""Shared utilities: logging, caching, validation helpers."""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from app import config

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
_LOGGER_NAME = "learnpath"


def setup_logging() -> None:
    level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    root = logging.getLogger(_LOGGER_NAME)
    root.setLevel(level)
    root.handlers = [handler]
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


setup_logging()
log = get_logger("app")

# ------------------------------------------------------------------
# Caching
# ------------------------------------------------------------------
def disk_cache(cache_dir: Path, key_prefix: str = "cache"):
    """Simple deterministic disk cache decorator for expensive pure functions.

    Serializes args to a hash key and stores JSON results under cache_dir.
    Returns the same object type on hit; None-safe.
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            payload = json.dumps(
                {"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}},
                sort_keys=True,
                default=str,
            )
            key = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
            cache_dir.mkdir(parents=True, exist_ok=True)
            path = cache_dir / f"{key_prefix}_{key}.json"
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
            result = func(*args, **kwargs)
            try:
                path.write_text(
                    json.dumps(result, default=str, ensure_ascii=False), encoding="utf-8"
                )
            except (TypeError, OSError) as exc:  # pragma: no cover - non-serializable results
                log.warning("disk cache write failed for %s: %s", func.__name__, exc)
            return result

        return wrapper

    return decorator


# ------------------------------------------------------------------
# Validation helpers
# ------------------------------------------------------------------
def safe_float(value: Any, default: float = 0.0, lo: float | None = None, hi: float | None = None) -> float:
    """Coerce a value to a float within [lo, hi], falling back to default."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def safe_int(value: Any, default: int = 0, lo: int | None = None, hi: int | None = None) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def require_text(text: str | None, min_len: int = 3) -> bool:
    return bool(text and text.strip() and len(text.strip()) >= min_len)


def split_list(value: str | list[str] | None) -> list[str]:
    """Normalize a semicolon/comma separated string or list into clean tokens."""
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = [value]
    out: list[str] = []
    for item in raw:
        for part in str(item).replace(";", ",").split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def safe_json(text: str | None) -> dict | None:
    """Parse LLM-ish JSON text defensively (strips code fences / prose)."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def now_ms() -> int:
    return int(time.time() * 1000)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
