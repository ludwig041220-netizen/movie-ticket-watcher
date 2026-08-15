from __future__ import annotations

import html
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import requests

from .models import SessionInfo, SourceResult, Target
from .notifiers import EmailNotifier, PushPlusNotifier
from .notifiers.base import BaseNotifier, Message, NotificationError
from .sources import MaoyanHtmlSource, MaoyanJsonSource
from .sources.base import BaseSource, SourceError
from .state import StateStore


LOGGER = logging.getLogger(__name__)


class AllSourcesFailed(RuntimeError):
    pass


def build_sources(
    configs: Iterable[Dict[str, Any]],
    session: requests.Session,
    timeout: float,
) -> List[BaseSource]:
    mapping = {
        "maoyan_json": MaoyanJsonSource,
        "maoyan_html": MaoyanHtmlSource,
    }
    sources: List[BaseSource] = []
    for config in configs:
        if not config.get("enabled", True):
            continue
        source_type = str(config.get("type") or "")
        source_class = mapping.get(source_type)
        if source_class is None:
            raise ValueError(f"不支持的数据源类型: {source_type}")
        sources.append(source_class(config, session, timeout))
    return sources


def build_notifiers(
    config: Dict[str, Any], session: requests.Session, timeout: float
) -> List[BaseNotifier]:
    notifiers: List[BaseNotifier] = []
    email_config = config.get("email") or {}
    if email_config.get("enabled", False):
        notifiers.append(EmailNotifier(email_config, timeout))
    push_config = config.get("pushplus") or {}
    if push_config.get("enabled", False):
        notifiers.append(PushPlusNotifier(push_config, session, timeout))
    return notifiers


def merge_sessions(results: Iterable[SourceResult]) -> List[SessionInfo]:
    merged: Dict[str, SessionInfo] = {}
    for result in results:
        for session in result.sessions:
            existing = merged.get(session.fingerprint)
            # Prefer the structured source, while retaining a fallback-only session.
            if existing is None or session.source.endswith("json"):
                merged[session.fingerprint] = session
    return sorted(merged.values(), key=lambda item: (item.date, item.time, item.hall))


def build_message(
    target: Target, sessions: Sequence[SessionInfo], discovered_at: datetime
) -> Message:
    subject = f"【开票提醒】{target.movie_name}｜{target.cinema_name}"
    found_time = discovered_at.strftime("%Y-%m-%d %H:%M:%S %Z")
    session_lines = [f"- {item.label()}" for item in sessions]
    text = "\n".join(
        [
            "发现新的可售场次，请尽快购票。",
            "",
            f"影院：{target.cinema_name}",
            f"影片：{target.movie_name}",
            f"日期：{target.date}",
            f"发现时间：{found_time}",
            "新增场次：",
            *session_lines,
            "",
            f"购票链接：{target.buy_url}",
        ]
    )
    list_items = "".join(f"<li>{html.escape(item.label())}</li>" for item in sessions)
    message_html = f"""
    <html><body>
      <h2>发现新的可售场次</h2>
      <p><strong>影院：</strong>{html.escape(target.cinema_name)}<br>
      <strong>影片：</strong>{html.escape(target.movie_name)}<br>
      <strong>日期：</strong>{html.escape(target.date)}<br>
      <strong>发现时间：</strong>{html.escape(found_time)}</p>
      <p><strong>新增场次：</strong></p><ul>{list_items}</ul>
      <p><a href="{html.escape(target.buy_url, quote=True)}">立即打开购票页面</a></p>
    </body></html>
    """.strip()
    return Message(subject=subject, text=text, html=message_html)


class WatcherService:
    def __init__(
        self,
        target: Target,
        sources: Sequence[BaseSource],
        notifiers: Sequence[BaseNotifier],
        state: StateStore,
        runtime: Dict[str, Any],
    ) -> None:
        self.target = target
        self.sources = list(sources)
        self.notifiers = list(notifiers)
        self.state = state
        self.runtime = runtime

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.target.timezone))

    def is_expired(self, now: datetime) -> bool:
        stop_days = int(self.runtime.get("stop_after_target_days", 1))
        return now.date() > date.fromisoformat(self.target.date) + timedelta(days=stop_days)

    def collect(self) -> Tuple[List[SessionInfo], List[SourceResult]]:
        successes: List[SourceResult] = []
        errors: List[str] = []
        for source in self.sources:
            try:
                result = source.check(self.target)
                successes.append(result)
                LOGGER.info(
                    "source=%s ok matched_movie=%s target_sessions=%d sellable=%d",
                    result.source,
                    result.matched_movie,
                    result.target_session_count,
                    len(result.sessions),
                )
            except SourceError as exc:
                errors.append(str(exc))
                LOGGER.warning("source=%s failed: %s", source.name, exc)
        if not successes:
            raise AllSourcesFailed("所有数据源均失败: " + " | ".join(errors))
        return merge_sessions(successes), successes

    def notify(self, message: Message) -> List[str]:
        delivered: List[str] = []
        errors: List[str] = []
        for notifier in self.notifiers:
            try:
                notifier.send(message)
                delivered.append(notifier.name)
                LOGGER.info("notification=%s delivered", notifier.name)
            except NotificationError as exc:
                errors.append(f"{notifier.name}: {exc}")
                LOGGER.error("notification=%s failed: %s", notifier.name, exc)
        if not delivered:
            raise NotificationError("所有通知渠道均失败: " + " | ".join(errors))
        return delivered

    def run_once(self, dry_run: bool = False) -> int:
        now = self.now()
        self.state.load()
        if self.is_expired(now):
            LOGGER.info("target=%s expired; skipping network check", self.target.id)
            self.state.heartbeat_if_due(
                now, int(self.runtime.get("heartbeat_days", 30))
            )
            self.state.save()
            return 0

        sessions, _ = self.collect()
        known = self.state.notified_ids(self.target.id)
        new_sessions = [item for item in sessions if item.fingerprint not in known]
        if not new_sessions:
            LOGGER.info(
                "target=%s no new sellable sessions (sellable=%d known=%d)",
                self.target.id,
                len(sessions),
                len(known),
            )
        else:
            message = build_message(self.target, new_sessions, now)
            if dry_run:
                LOGGER.warning("dry-run: would notify %d new session(s)", len(new_sessions))
                LOGGER.info("dry-run message:\n%s", message.text)
            else:
                if not self.notifiers:
                    raise NotificationError("没有启用任何通知渠道")
                self.notify(message)
                self.state.mark_notified(
                    self.target.id,
                    (item.fingerprint for item in new_sessions),
                    now,
                )

        self.state.heartbeat_if_due(now, int(self.runtime.get("heartbeat_days", 30)))
        self.state.save()
        return len(new_sessions)

    def send_test_notification(self) -> None:
        if not self.notifiers:
            raise NotificationError("没有启用任何通知渠道")
        example = SessionInfo(
            source="test",
            date=self.target.date,
            time="19:30",
            hall="IMAX 激光厅（测试）",
            language="英语",
            format="IMAX2D",
            buy_url=self.target.buy_url,
        )
        message = build_message(self.target, [example], self.now())
        test_message = Message(
            subject=f"【测试通知】{message.subject}",
            text="这是一条部署测试通知，不代表已经开票。\n\n" + message.text,
            html=(
                "<p><strong>这是一条部署测试通知，不代表已经开票。</strong></p>"
                + message.html
            ),
        )
        self.notify(test_message)
