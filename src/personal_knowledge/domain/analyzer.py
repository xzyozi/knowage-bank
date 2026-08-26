"""検索履歴から技術的調査セッションを抽出・解析するモジュール。"""

from datetime import datetime, timezone

from personal_knowledge.domain.models import SearchEntry, SearchSession


class SessionAnalyzer:
    """連続した検索ログを時間間隔に基づいて調査セッションにグループ化・解析するクラス。"""

    def __init__(self, session_gap_seconds: int = 1800, min_queries: int = 2) -> None:
        """SessionAnalyzer を初期化する。

        Args:
            session_gap_seconds: 同一セッションとみなす最大時間間隔 (デフォルト: 1800秒 = 30分)。
            min_queries: 有効セッションとみなす最小クエリ件数 (デフォルト: 2件。1件のみの単発検索は破棄)。
        """
        self.session_gap_seconds = session_gap_seconds
        self.min_queries = min_queries

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """タイムゾーン情報がない datetime に UTC を付与する。"""
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    def analyze_sessions(self, entries: list[SearchEntry]) -> list[SearchSession]:
        """検索エントリ群を 30 分以内の連続検索セッションにグループ化し、単発検索を破棄する。

        Args:
            entries: 重複排除済みの検索エントリリスト。

        Returns:
            list[SearchSession]: 抽出された有効な調査セッション一覧。
        """
        if not entries:
            return []

        sorted_entries = sorted(entries, key=lambda x: self._ensure_utc(x.timestamp))

        raw_sessions: list[list[SearchEntry]] = []
        current_group: list[SearchEntry] = []

        for entry in sorted_entries:
            if not current_group:
                current_group.append(entry)
                continue

            last_entry = current_group[-1]
            curr_ts = self._ensure_utc(entry.timestamp)
            last_ts = self._ensure_utc(last_entry.timestamp)
            gap = (curr_ts - last_ts).total_seconds()

            if 0 <= gap <= self.session_gap_seconds:
                current_group.append(entry)
            else:
                raw_sessions.append(current_group)
                current_group = [entry]

        if current_group:
            raw_sessions.append(current_group)

        valid_sessions: list[SearchSession] = []
        for group in raw_sessions:
            # クエリ件数が min_queries 未満 (単発検索) はノイズとみなして破棄
            if len(group) < self.min_queries:
                continue

            start_time = self._ensure_utc(group[0].timestamp)
            end_time = self._ensure_utc(group[-1].timestamp)
            queries = [e.keyword for e in group]

            browsers_set: set[str] = set()
            for e in group:
                for b in e.source_browser.split(","):
                    cleaned_b = b.strip()
                    if cleaned_b:
                        browsers_set.add(cleaned_b)

            valid_sessions.append(
                SearchSession(
                    start_time=start_time,
                    end_time=end_time,
                    queries=queries,
                    source_browsers=sorted(browsers_set),
                )
            )

        return valid_sessions
