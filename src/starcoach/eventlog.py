"""Append-only JSONL event log. Every run, tool call, decision and error goes here."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import mask

DEFAULT_LOG = Path("logs") / "events.jsonl"


class EventLog:
    def __init__(self, path: Path | None = None, secrets: list[str] | None = None):
        self.path = Path(os.environ.get("STARCOACH_LOG", path or DEFAULT_LOG))
        self.secrets = secrets or []
        self.run_id = uuid.uuid4().hex[:12]

    def write(self, kind: str, **data) -> dict:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run": self.run_id,
            "kind": kind,
            **data,
        }
        line = mask(json.dumps(event, ensure_ascii=False, default=str), self.secrets)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return json.loads(line)
