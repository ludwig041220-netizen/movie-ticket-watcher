from typing import Any, Dict

from movie_watcher.models import Target
from movie_watcher.sources.maoyan import MaoyanJsonSource


class FakeResponse:
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return self.payload


class FakeSession:
    headers = {"User-Agent": "test"}

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        return FakeResponse(self.payload)


TARGET = Target(
    id="target",
    cinema_name="MOViE MOViE 影城（前滩太古里店）",
    cinema_id="37534",
    movie_name="奥德赛",
    movie_id="1545360",
    date="2026-08-21",
    timezone="Asia/Shanghai",
    buy_url="https://example.test/buy",
)


def test_json_source_filters_date_and_sellable_status() -> None:
    payload = {
        "showData": {
            "cinemaName": "MOViE MOViE 影城（前滩太古里店）",
            "movies": [
                {
                    "id": 1545360,
                    "nm": "奥德赛",
                    "shows": [
                        {
                            "showDate": "2026-08-21",
                            "plist": [
                                {
                                    "dt": "2026-08-21",
                                    "tm": "19:30",
                                    "th": "IMAX 激光厅",
                                    "lang": "英语",
                                    "tp": "IMAX2D",
                                    "seqNo": "available",
                                    "ticketStatus": 0,
                                },
                                {
                                    "dt": "2026-08-21",
                                    "tm": "22:45",
                                    "th": "IMAX 激光厅",
                                    "lang": "英语",
                                    "tp": "IMAX2D",
                                    "seqNo": "sold-out",
                                    "ticketStatus": 1,
                                },
                            ],
                        },
                        {
                            "showDate": "2026-08-20",
                            "plist": [
                                {
                                    "dt": "2026-08-20",
                                    "tm": "19:30",
                                    "ticketStatus": 0,
                                }
                            ],
                        },
                    ],
                }
            ],
        }
    }
    source = MaoyanJsonSource(
        {"name": "maoyan_json", "type": "maoyan_json"},
        FakeSession(payload),  # type: ignore[arg-type]
        10,
    )
    result = source.check(TARGET)

    assert result.matched_movie is True
    assert result.target_session_count == 2
    assert [item.external_id for item in result.sessions] == ["available"]


def test_json_source_handles_movie_not_returned() -> None:
    payload = {
        "showData": {
            "cinemaName": TARGET.cinema_name,
            "movies": [{"id": 999, "nm": "别的电影", "shows": []}],
        }
    }
    source = MaoyanJsonSource(
        {"name": "maoyan_json", "type": "maoyan_json"},
        FakeSession(payload),  # type: ignore[arg-type]
        10,
    )
    result = source.check(TARGET)
    assert result.matched_movie is False
    assert result.sessions == []

