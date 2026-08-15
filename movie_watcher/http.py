from __future__ import annotations

from typing import Any, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_HEADERS = {
    "Accept": "application/json,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
}


def build_http_session(runtime: Dict[str, Any]) -> requests.Session:
    retries = int(runtime.get("retries", 3))
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=float(runtime.get("retry_backoff_factor", 1.0)),
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

