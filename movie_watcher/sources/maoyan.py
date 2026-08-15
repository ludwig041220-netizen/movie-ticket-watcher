from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..models import SessionInfo, SourceResult, Target, normalize_text
from .base import BaseSource, SourceError


def _matches_name(actual: Any, expected: str) -> bool:
    left, right = normalize_text(actual), normalize_text(expected)
    return bool(left and right and (left == right or left in right or right in left))


class MaoyanJsonSource(BaseSource):
    """Parser for Maoyan's public mobile cinema-detail response."""

    def check(self, target: Target) -> SourceResult:
        endpoint = str(
            self.config.get("endpoint") or "https://i.maoyan.com/ajax/cinemaDetail"
        )
        params = {
            "cinemaId": target.cinema_id,
            "movieId": target.movie_id,
            "_v_": "yes",
        }
        try:
            response = self.session.get(endpoint, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise SourceError(f"{self.name}: JSON 请求/解析失败: {exc}") from exc

        show_data = payload.get("showData") or {}
        actual_cinema = str(show_data.get("cinemaName") or "")
        if not actual_cinema:
            raise SourceError(f"{self.name}: 响应缺少影院信息，可能是接口结构变化或拦截页")
        if not _matches_name(actual_cinema, target.cinema_name):
            raise SourceError(
                f"{self.name}: 影院不匹配，返回 {actual_cinema!r}，预期 {target.cinema_name!r}"
            )

        expected_id = str(target.movie_id)
        movies = show_data.get("movies") or []
        movie: Optional[Dict[str, Any]] = next(
            (item for item in movies if str(item.get("id")) == expected_id), None
        )
        if movie is None:
            movie = next(
                (item for item in movies if _matches_name(item.get("nm"), target.movie_name)),
                None,
            )
        if movie is None:
            return SourceResult(
                source=self.name,
                matched_movie=False,
                details={"cinema": actual_cinema, "movies_returned": len(movies)},
            )

        raw_statuses = self.config.get("sellable_ticket_statuses", [0])
        sellable_statuses: Set[int] = {int(value) for value in raw_statuses}
        sessions: List[SessionInfo] = []
        target_session_count = 0

        for day in movie.get("shows") or []:
            if str(day.get("showDate")) != target.date:
                continue
            for show in day.get("plist") or []:
                if str(show.get("dt") or day.get("showDate")) != target.date:
                    continue
                target_session_count += 1
                try:
                    status = int(show.get("ticketStatus"))
                except (TypeError, ValueError):
                    status = -999
                if status not in sellable_statuses:
                    continue
                sessions.append(
                    SessionInfo(
                        source=self.name,
                        date=target.date,
                        time=str(show.get("tm") or "未知时间"),
                        hall=str(show.get("th") or ""),
                        language=str(show.get("lang") or ""),
                        format=str(show.get("tp") or ""),
                        buy_url=target.buy_url,
                        external_id=str(show.get("seqNo") or ""),
                        raw_status=str(status),
                    )
                )

        return SourceResult(
            source=self.name,
            sessions=sessions,
            matched_movie=True,
            target_session_count=target_session_count,
            details={"cinema": actual_cinema, "movie": movie.get("nm")},
        )


class MaoyanHtmlSource(BaseSource):
    """Conservative fallback for the public desktop cinema page."""

    STOP_WORDS = ("已售罄", "停售", "停止售票", "不可售", "放映结束", "已结束")
    BUY_WORDS = ("选座购票", "购票", "预售")

    def check(self, target: Target) -> SourceResult:
        url = str(self.config.get("url") or target.buy_url)
        headers = {"User-Agent": self.session.headers["User-Agent"].replace("iPhone", "Macintosh")}
        try:
            response = self.session.get(url, timeout=self.timeout, headers=headers)
            response.raise_for_status()
        except Exception as exc:
            raise SourceError(f"{self.name}: HTML 请求失败: {exc}") from exc

        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower() and "<html" not in response.text[:500].lower():
            raise SourceError(f"{self.name}: 返回内容不是 HTML")

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        if not _matches_name(page_text, target.cinema_name) and not _matches_name(
            page_text, target.movie_name
        ):
            raise SourceError(f"{self.name}: 页面不含目标影院或影片，可能是拦截页")
        if not _matches_name(page_text, target.movie_name):
            return SourceResult(source=self.name, matched_movie=False)

        sessions: List[SessionInfo] = []
        seen_rows: Set[int] = set()
        target_session_count = 0
        date_nodes = soup.select(f'[data-day="{target.date}"], [data-date="{target.date}"]')

        for date_node in date_nodes:
            block = self._closest_movie_block(date_node)
            if block is not None and not _matches_name(
                block.get_text(" ", strip=True), target.movie_name
            ):
                continue
            containers = self._containers_for_date(date_node, block or soup)
            for row in self._rows(containers):
                marker = id(row)
                if marker in seen_rows:
                    continue
                seen_rows.add(marker)
                row_text = row.get_text(" ", strip=True)
                if not re.search(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", row_text):
                    continue
                target_session_count += 1
                if any(word in row_text for word in self.STOP_WORDS):
                    continue
                if not any(word in row_text for word in self.BUY_WORDS):
                    continue
                sessions.append(self._parse_row(row, target, url))

        return SourceResult(
            source=self.name,
            sessions=sessions,
            matched_movie=True,
            target_session_count=target_session_count,
            details={"date_markers": len(date_nodes)},
        )

    @staticmethod
    def _closest_movie_block(node: Tag) -> Optional[Tag]:
        return node.find_parent(class_=re.compile(r"(?:show-list|movie-show|showtime)"))

    @staticmethod
    def _containers_for_date(date_node: Tag, root: Tag) -> List[Tag]:
        index = date_node.get("data-index")
        if index is not None:
            matches = root.select(
                f'.plist-container[data-index="{index}"], '
                f'.show-list-container[data-index="{index}"]'
            )
            if matches:
                return matches
        active = root.select(".plist-container.active, .show-list-container.active")
        return active or [root]

    @staticmethod
    def _rows(containers: Iterable[Tag]) -> Iterable[Tag]:
        for container in containers:
            yield from container.select("tr, .show-item")

    def _parse_row(self, row: Tag, target: Target, page_url: str) -> SessionInfo:
        text = row.get_text(" ", strip=True)
        time_node = row.select_one(".begin-time, .show-time, .time")
        time_match = re.search(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", text)
        show_time = (
            time_node.get_text(" ", strip=True) if time_node is not None else time_match.group(0)
        )
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        language_format = cells[1] if len(cells) > 1 else ""
        hall = cells[2] if len(cells) > 2 else ""
        link = row.select_one("a[href]")
        buy_url = urljoin(page_url, link.get("href")) if link is not None else target.buy_url
        return SessionInfo(
            source=self.name,
            date=target.date,
            time=show_time,
            hall=hall,
            language=language_format,
            buy_url=buy_url,
            external_id=str(row.get("data-id") or row.get("data-seq") or ""),
            raw_status="html-buy-link",
        )
