from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Set


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: Dict[str, Any] = {"version": 1, "targets": {}, "meta": {}}
        self.dirty = False

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"状态文件读取失败 {self.path}: {exc}") from exc
        if not isinstance(loaded, dict) or loaded.get("version") != 1:
            raise RuntimeError(f"不支持的状态文件版本: {self.path}")
        self.data = loaded
        self.data.setdefault("targets", {})
        self.data.setdefault("meta", {})

    def notified_ids(self, target_id: str) -> Set[str]:
        target_state = self.data["targets"].get(target_id) or {}
        return set(target_state.get("notified_session_ids") or [])

    def mark_notified(
        self, target_id: str, session_ids: Iterable[str], notified_at: datetime
    ) -> None:
        target_state = self.data["targets"].setdefault(target_id, {})
        known = set(target_state.get("notified_session_ids") or [])
        known.update(session_ids)
        target_state["notified_session_ids"] = sorted(known)
        target_state["last_notified_at"] = notified_at.isoformat()
        self.dirty = True

    def heartbeat_if_due(self, now: datetime, days: int) -> None:
        if days <= 0:
            return
        value = self.data["meta"].get("last_heartbeat")
        try:
            previous = datetime.fromisoformat(value) if value else None
            if previous is not None and previous.tzinfo is None:
                previous = previous.replace(tzinfo=now.tzinfo)
        except (TypeError, ValueError):
            previous = None
        if previous is None or now - previous >= timedelta(days=days):
            self.data["meta"]["last_heartbeat"] = now.isoformat()
            self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(str(temporary), str(self.path))
        self.dirty = False

