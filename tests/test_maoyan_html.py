from typing import Any

from movie_watcher.models import Target
from movie_watcher.sources.maoyan import MaoyanHtmlSource


class FakeResponse:
    headers = {"Content-Type": "text/html; charset=utf-8"}

    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    headers = {"User-Agent": "test iPhone"}

    def __init__(self, text: str) -> None:
        self.text = text

    def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        return FakeResponse(self.text)


def test_html_fallback_requires_target_date_and_buyable_row() -> None:
    html = """
    <html><body>
      <section class="show-list">
        <div class="movie-info"><span class="name">奥德赛</span></div>
        <span class="date-item" data-day="2026-08-21" data-index="7">8月21日</span>
        <div class="plist-container" data-index="7">
          <table>
            <tr><th>放映时间</th></tr>
            <tr data-seq="one">
              <td><span class="begin-time">19:30</span></td>
              <td>英语IMAX2D</td><td>IMAX 激光厅</td><td><a href="/buy/one">选座购票</a></td>
            </tr>
            <tr data-seq="two">
              <td><span class="begin-time">22:45</span></td>
              <td>英语IMAX2D</td><td>IMAX 激光厅</td><td>已售罄</td>
            </tr>
          </table>
        </div>
      </section>
    </body></html>
    """
    target = Target(
        id="target",
        cinema_name="MOViE MOViE 影城（前滩太古里店）",
        cinema_id="37534",
        movie_name="奥德赛",
        movie_id="1545360",
        date="2026-08-21",
        timezone="Asia/Shanghai",
        buy_url="https://example.test/cinema",
    )
    source = MaoyanHtmlSource(
        {"name": "html", "url": target.buy_url},
        FakeSession(html),  # type: ignore[arg-type]
        10,
    )
    result = source.check(target)
    assert result.target_session_count == 2
    assert len(result.sessions) == 1
    assert result.sessions[0].time == "19:30"
    assert result.sessions[0].buy_url == "https://example.test/buy/one"

