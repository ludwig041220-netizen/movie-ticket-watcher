from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from .models import Target


class ConfigError(ValueError):
    pass


def _required(mapping: Dict[str, Any], key: str) -> Any:
    value = mapping.get(key)
    if value is None or str(value).strip() == "":
        raise ConfigError(f"缺少配置项: {key}")
    return value


def load_config(path: Path) -> Tuple[Target, Dict[str, Any]]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 格式错误: {exc}") from exc

    target_raw = raw.get("target") or {}
    target_date = _required(target_raw, "date")
    if isinstance(target_date, date):
        target_date = target_date.isoformat()
    target_date = str(target_date)
    try:
        date.fromisoformat(target_date)
    except ValueError as exc:
        raise ConfigError("target.date 必须是 YYYY-MM-DD") from exc

    target = Target(
        id=str(_required(target_raw, "id")),
        cinema_name=str(_required(target_raw, "cinema_name")),
        cinema_id=str(_required(target_raw, "cinema_id")),
        movie_name=str(_required(target_raw, "movie_name")),
        movie_id=str(_required(target_raw, "movie_id")),
        date=target_date,
        timezone=str(target_raw.get("timezone") or "Asia/Shanghai"),
        buy_url=str(_required(target_raw, "buy_url")),
    )

    sources = raw.get("sources")
    if not isinstance(sources, list) or not any(s.get("enabled", True) for s in sources):
        raise ConfigError("至少需要一个启用的数据源")
    raw.setdefault("notifications", {})
    raw.setdefault("runtime", {})
    return target, raw

