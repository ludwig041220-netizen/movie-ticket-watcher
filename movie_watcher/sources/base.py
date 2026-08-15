from __future__ import annotations

from typing import Any, Dict

import requests

from ..models import SourceResult, Target


class SourceError(RuntimeError):
    pass


class BaseSource:
    def __init__(
        self,
        config: Dict[str, Any],
        session: requests.Session,
        timeout: float,
    ) -> None:
        self.config = config
        self.session = session
        self.timeout = timeout
        self.name = str(config.get("name") or config.get("type") or "source")

    def check(self, target: Target) -> SourceResult:
        raise NotImplementedError

