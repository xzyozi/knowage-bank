"""Chromium 系ブラウザ (Chrome, Edge) の検索履歴データアクセスモジュール。"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, unquote_plus, urlparse

from personal_knowledge.dao.base_dao import BrowserHistoryDAO
from personal_knowledge.domain.models import SearchEntry


class ChromiumHistoryDAO(BrowserHistoryDAO):
    """Google Chrome および Microsoft Edge の履歴 DB から検索ログを抽出する DAO クラス。"""

    def __init__(self, browser_type: str = "chrome", history_path: Path | None = None) -> None:
        """ChromiumHistoryDAO を初期化する。

        Args:
            browser_type: ブラウザ識別子 ('chrome' または 'edge')。
            history_path: カスタム履歴ファイルパス。None の場合は標準パスを使用。
        """
        super().__init__(history_path=history_path)
        self._browser_type = browser_type.lower()

    @property
    def browser_name(self) -> str:
        """ブラウザの識別子名称を取得する。

        Returns:
            str: 'chrome' または 'edge'。
        """
        return self._browser_type

    @property
    def default_history_path(self) -> Path:
        """Windows 標準の Chromium 履歴ファイルパスを取得する。

        Returns:
            Path: 標準プロファイルパス。
        """
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        base_dir = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"

        if self._browser_type == "edge":
            return base_dir / "Microsoft" / "Edge" / "User Data" / "Default" / "History"
        return base_dir / "Google" / "Chrome" / "User Data" / "Default" / "History"

    @staticmethod
    def _convert_webkit_time(webkit_timestamp: int) -> datetime | None:
        """WebKit タイムスタンプ (1601-01-01 基準マイクロ秒) を UTC datetime に変換する。

        Args:
            webkit_timestamp: WebKit タイムスタンプ整数値。

        Returns:
            datetime | None: 変換後の UTC datetime。不正な場合は None。
        """
        if not webkit_timestamp or webkit_timestamp <= 0:
            return None
        try:
            # 1601-01-01 と 1970-01-01 の差分秒: 11644473600
            epoch_seconds = (webkit_timestamp / 1_000_000) - 11644473600
            if epoch_seconds <= 0:
                return None
            return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    @staticmethod
    def _extract_query_from_url(url: str) -> str | None:
        """URL から検索クエリ (Google / Bing / Yahoo 等) を抽出する。

        Args:
            url: URL 文字列。

        Returns:
            str | None: 抽出・デコードされた検索クエリ。
        """
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            for param_key in ["q", "query", "p"]:
                if param_key in query_params and query_params[param_key]:
                    val = query_params[param_key][0].strip()
                    if val:
                        return unquote_plus(val)
        except Exception:
            return None
        return None

    def _extract_from_sqlite(self, db_path: Path, limit: int) -> list[SearchEntry]:
        """一時コピーされた Chromium 履歴 SQLite DB から検索履歴エントリを抽出する。

        Args:
            db_path: 一時 SQLite ファイルパス。
            limit: 取得最大件数。

        Returns:
            list[SearchEntry]: 抽出された検索エントリ一覧。
        """
        entries: list[SearchEntry] = []
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            query_sql = """
                SELECT url, title, last_visit_time
                FROM urls
                WHERE url LIKE '%google.%/search?%'
                   OR url LIKE '%bing.com/search?%'
                   OR url LIKE '%duckduckgo.com/?%'
                   OR url LIKE '%yahoo.co.jp/search%'
                ORDER BY last_visit_time DESC
                LIMIT ?
            """
            cursor.execute(query_sql, (limit,))
            rows = cursor.fetchall()

            for row in rows:
                url = str(row["url"]) if row["url"] else ""
                last_visit_time = row["last_visit_time"]
                keyword = self._extract_query_from_url(url)
                if not keyword:
                    continue

                dt = self._convert_webkit_time(last_visit_time)
                if dt is None:
                    continue

                entries.append(
                    SearchEntry(
                        timestamp=dt,
                        keyword=keyword,
                        source_browser=self.browser_name,
                    )
                )
        finally:
            conn.close()

        return entries
