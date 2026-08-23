"""検索履歴の重複排除を行うドメインロジックモジュール。"""

from datetime import datetime, timezone
import re

from personal_knowledge.domain.models import SearchEntry


class SessionDeduplicator:
    """時系列検索エントリ群から短時間の重複を排除・統合するクラス。"""

    def __init__(self, time_window_seconds: int = 300) -> None:
        """SessionDeduplicator を初期化する。

        Args:
            time_window_seconds: 重複とみなす最大時間間隔 (デフォルト: 300秒 = 5分)。
        """
        self.time_window_seconds = time_window_seconds

    @staticmethod
    def _normalize_keyword(keyword: str) -> str:
        """キーワードの空白および大文字小文字を正規化する。

        Args:
            keyword: 生のキーワード文字列。

        Returns:
            str: 正規化されたキーワード文字列。
        """
        return re.sub(r"\s+", " ", keyword.strip().lower())

    def deduplicate(self, entries: list[SearchEntry]) -> list[SearchEntry]:
        """5分以内に発生した同一キーワードの検索を1つにマージする。

        マージ時は source_browser を統合してトレーサビリティを保持する。

        Args:
            entries: 生の検索エントリリスト。

        Returns:
            list[SearchEntry]: 重複排除・統合後の検索エントリリスト (時系列昇順)。
        """
        if not entries:
            return []

        def _ensure_utc(dt: datetime) -> datetime:
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

        # タイムスタンプ昇順でソート
        sorted_entries = sorted(entries, key=lambda x: _ensure_utc(x.timestamp))
        deduped: list[SearchEntry] = []

        for current in sorted_entries:
            if not deduped:
                deduped.append(current)
                continue

            last = deduped[-1]
            last_norm = self._normalize_keyword(last.keyword)
            curr_norm = self._normalize_keyword(current.keyword)

            curr_ts = _ensure_utc(current.timestamp)
            last_ts = _ensure_utc(last.timestamp)
            time_diff = (curr_ts - last_ts).total_seconds()

            # 5分以内の同一キーワードであるか判定
            if curr_norm == last_norm and 0 <= time_diff <= self.time_window_seconds:
                # source_browser を統合
                existing_browsers = [b.strip() for b in last.source_browser.split(",") if b.strip()]
                curr_browser = current.source_browser.strip()
                if curr_browser not in existing_browsers:
                    existing_browsers.append(curr_browser)
                    last.source_browser = ", ".join(sorted(existing_browsers))
            else:
                deduped.append(current)

        return deduped
