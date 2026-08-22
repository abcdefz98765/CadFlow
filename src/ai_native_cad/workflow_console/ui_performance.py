"""Opt-in, product-safe timing events for local NiceGUI profiling."""

from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any


def ui_trace_enabled() -> bool:
    return os.getenv("CADFLOW_UI_TRACE") == "1"


def ui_trace_start() -> float:
    return perf_counter()


def ui_trace_event(name: str, started_at: float, **fields: Any) -> None:
    if not ui_trace_enabled():
        return
    safe_fields = {
        key: value
        for key, value in fields.items()
        if value is None or isinstance(value, (bool, int, float, str))
    }
    print(
        "[cadflow-ui-trace] "
        + json.dumps(
            {
                "name": name,
                "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                **safe_fields,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        flush=True,
    )
