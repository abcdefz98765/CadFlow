"""Tiny env-file loader for manual provider smoke scripts."""

from __future__ import annotations

import os
from pathlib import Path


def parse_env_file(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if not key or any(part in key for part in ("/", "\\", ":", " ")):
            continue
        values[key] = _strip_quotes(value.strip())
    return values


def load_env_file(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    loaded: dict[str, str] = {}
    values = parse_env_file(Path(path).read_text(encoding="utf-8"))
    for key, value in values.items():
        if key in os.environ:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
