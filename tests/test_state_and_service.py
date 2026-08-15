from datetime import datetime
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from movie_watcher.models import SessionInfo, SourceResult, Target
from movie_watcher.notifiers.base import BaseNotifier, Message
from movie_watcher.service import WatcherService, merge_sessions
from movie_watcher.state import StateStore


class FakeSource:
    name = "fake"

    def __init__(self, sessions: List[SessionInfo]) -> None:
        self.sessions = sessions

    def check(self, target: Target) -> SourceResult:
        return SourceResult(
            source=self.name,
            sessions=self.sessions,
            matched_movie=True,
            target_session_count=len(self.sessions),
        )


class FakeNotifier(BaseNotifier):
    name = "fake-notifier"

    def __init__(self) -> None:
        self.messages: List[Message] = []

    def send(self, message: Message) -> None:
        self.messages.append(message)


class FixedWatcher(WatcherService):
    def now(self) -> datetime:
        return datetime(2026, 8, 15, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_notifies_once_for_same_session(tmp_path: Path) -> None:
    target = Target(
        id="target",
        cinema_name="影院",
        cinema_id="1",
        movie_name="电影",
        movie_id="2",
        date="2026-08-21",
        timezone="Asia/Shanghai",
        buy_url="https://example.test",
    )
    session = SessionInfo(
        source="fake",
        date=target.date,
        time="19:30",
        hall="1号厅",
        language="英语",
        format="2D",
    )
    notifier = FakeNotifier()
    state_path = tmp_path / "state.json"

    first = FixedWatcher(
        target,
        [FakeSource([session])],  # type: ignore[list-item]
        [notifier],
        StateStore(state_path),
        {"heartbeat_days": 30},
    )
    assert first.run_once() == 1
    second = FixedWatcher(
        target,
        [FakeSource([session])],  # type: ignore[list-item]
        [notifier],
        StateStore(state_path),
        {"heartbeat_days": 30},
    )
    assert second.run_once() == 0
    assert len(notifier.messages) == 1


def test_dry_run_does_not_persist_dedup_state(tmp_path: Path) -> None:
    target = Target(
        id="target",
        cinema_name="影院",
        cinema_id="1",
        movie_name="电影",
        movie_id="2",
        date="2026-08-21",
        timezone="Asia/Shanghai",
        buy_url="https://example.test",
    )
    session = SessionInfo(source="fake", date=target.date, time="19:30")
    state = StateStore(tmp_path / "state.json")
    watcher = FixedWatcher(
        target,
        [FakeSource([session])],  # type: ignore[list-item]
        [],
        state,
        {"heartbeat_days": 0},
    )
    assert watcher.run_once(dry_run=True) == 1
    assert not state.path.exists()


def test_json_and_html_versions_of_same_session_merge() -> None:
    json_session = SessionInfo(
        source="maoyan_json",
        date="2026-08-21",
        time="19:30",
        hall="IMAX 激光厅",
        language="英语",
        format="IMAX2D",
        external_id="123",
    )
    html_session = SessionInfo(
        source="maoyan_html_fallback",
        date="2026-08-21",
        time="19:30",
        hall="IMAX 激光厅",
        language="英语IMAX2D",
    )
    merged = merge_sessions(
        [
            SourceResult(source="maoyan_json", sessions=[json_session]),
            SourceResult(source="maoyan_html_fallback", sessions=[html_session]),
        ]
    )
    assert len(merged) == 1
    assert merged[0].external_id == "123"
