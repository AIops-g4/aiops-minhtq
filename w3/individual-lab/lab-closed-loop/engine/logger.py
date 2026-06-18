"""Structured JSON logging for the closed-loop orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class JsonLogger:
    """Emit one machine-readable JSON event per stdout line."""

    def _emit(self, level: str, event_type: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event_type": event_type,
            "service": fields.pop("service", None),
            "action": fields.pop("action", None),
            "result": fields.pop("result", None),
            **fields,
        }
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def info(self, event_type: str, **fields: Any) -> None:
        self._emit("INFO", event_type, **fields)

    def warning(self, event_type: str, **fields: Any) -> None:
        self._emit("WARNING", event_type, **fields)

    def error(self, event_type: str, **fields: Any) -> None:
        self._emit("ERROR", event_type, **fields)
