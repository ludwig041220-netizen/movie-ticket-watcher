from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ConfigError, load_config
from .http import build_http_session
from .notifiers.base import NotificationError
from .service import AllSourcesFailed, WatcherService, build_notifiers, build_sources
from .state import StateStore


def configure_logging(log_file: Path, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - %(message)s", "%Y-%m-%dT%H:%M:%S%z"
    )
    root = logging.getLogger()
    root.setLevel(level)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="电影开票监测器")
    parser.add_argument("--config", default="config.yaml", type=Path)
    parser.add_argument("--state", default="runtime/state.json", type=Path)
    parser.add_argument("--log-file", default="runtime/watcher.log", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="检查但不通知、不去重")
    parser.add_argument(
        "--test-notification", action="store_true", help="发送一条测试通知后退出"
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_file, args.verbose)
    logger = logging.getLogger(__name__)
    try:
        target, config = load_config(args.config)
        runtime = config.get("runtime") or {}
        timeout = float(runtime.get("request_timeout_seconds", 20))
        session = build_http_session(runtime)
        sources = build_sources(config["sources"], session, timeout)
        notifiers = build_notifiers(config.get("notifications") or {}, session, timeout)
        service = WatcherService(
            target=target,
            sources=sources,
            notifiers=notifiers,
            state=StateStore(args.state),
            runtime=runtime,
        )
        if args.test_notification:
            service.send_test_notification()
            logger.info("test notification delivered")
            return 0
        service.run_once(dry_run=args.dry_run)
        return 0
    except ConfigError as exc:
        logger.error("configuration error: %s", exc)
        return 4
    except AllSourcesFailed as exc:
        logger.error("source error: %s", exc)
        return 2
    except NotificationError as exc:
        logger.error("notification error: %s", exc)
        return 3
    except Exception:
        logger.exception("unexpected error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

