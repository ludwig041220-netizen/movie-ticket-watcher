from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


def normalize_text(value: Any) -> str:
    """Normalize user/platform text for conservative name matching."""
    return re.sub(r"[\s·・•（）()\-—_]", "", str(value or "")).casefold()


@dataclass(frozen=True)
class Target:
    id: str
    cinema_name: str
    cinema_id: str
    movie_name: str
    movie_id: str
    date: str
    timezone: str
    buy_url: str


@dataclass(frozen=True)
class SessionInfo:
    source: str
    date: str
    time: str
    hall: str = ""
    language: str = ""
    format: str = ""
    buy_url: str = ""
    external_id: str = ""
    raw_status: str = ""

    @property
    def fingerprint(self) -> str:
        # Deliberately source-independent so the JSON and HTML sources merge.
        # HTML often combines "英语" and "IMAX2D" in one table cell, while JSON
        # returns them separately, so language+format is normalized as one field.
        raw = "|".join(
            (
                normalize_text(self.date),
                normalize_text(self.time),
                normalize_text(self.hall),
                normalize_text(self.language + self.format),
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def label(self) -> str:
        parts = [self.time, self.language, self.format, self.hall]
        return " / ".join(p for p in parts if p)


@dataclass
class SourceResult:
    source: str
    sessions: List[SessionInfo] = field(default_factory=list)
    matched_movie: bool = False
    target_session_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
