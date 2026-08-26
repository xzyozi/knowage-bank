"""Mozilla Firefox の検索履歴データアクセスモジュール。"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, unquote_plus, urlparse

from personal_knowledge.dao.base_dao import BrowserHistoryDAO
from personal_knowledge.domain.models import SearchEntry


class FirefoxHistoryDAO(BrowserHistoryDAO):
    """Mozilla Firefox の places.sqlite から検索ログを抽出する DAO クラス。"""

    def __init__(self, history_path: Path | None = None) -> None:
        """FirefoxHistoryDAO を初期化する。

        Args:
            history_path: カスタム places.sqlite パス。None の場合はプロファイル自動検出。
        """
        super().__init__(history_path=history_path)

    @property
    def browser_name(self) -> str:
        """ブラウザの識別子名称を取得する。

        Returns:
            str: 'firefox'。
        """
        return "firefox"

    @property
    def default_history_path(self) -> Path:
        """Windows 標準の Firefox プロファイル配下の places.sqlite を探索・取得する。

        Returns:
            Path: places.sqlite パス（見つからない場合は探索ベースパス）。
        """
        appdata = os.environ.get("APPDATA", "")
        base_dir = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        profiles_dir = base_dir / "Mozilla" / "Firefox" / "Profiles"

        if profiles_dir.exists():
            # release または default を含むプロファイルディレクトリを優先探索
            for profile_path in sorted(profiles_dir.iterdir()):
                if profile_path.is_dir():
                    places_file = profile_path / "places.sqlite"
                    if places_file.exists():
                        return places_file

        return profiles_dir / "default" / "places.sqlite"

    @staticmethod
    def _convert_prtime(prtime: int) -> datetime | None:
        """Firefox PRTime (1970-01-01 基準マイクロ秒) を UTC datetime に変換する。

        Args:
            prtime: PRTime 整数値。

        Returns:
            datetime | None: 変換後の UTC datetime。不正な場合は None。
        """
        if not prtime or prtime <= 0:
            return None
        try:
            epoch_seconds = prtime / 1_000_000
            return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    @staticmethod
    def _extract_query_from_url(url: str) -> str | None:
        """URL から検索クエリを抽出する。

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
        """一時コピーされた Firefox places.sqlite から検索履歴エントリを抽出する。

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
                SELECT url, title, last_visit_date
                FROM moz_places
                WHERE (url LIKE '%google.%/search?%'
                   OR url LIKE '%bing.com/search?%'
                   OR url LIKE '%duckduckgo.com/?%'
                   OR url LIKE '%yahoo.co.jp/search%')
                  AND last_visit_date IS NOT NULL
                ORDER BY last_visit_date DESC
                LIMIT ?
            """
            cursor.execute(query_sql, (limit,))
            rows = cursor.fetchall()

            for row in rows:
                url = str(row["url"]) if row["url"] else ""
                last_visit_date = row["last_visit_date"]
                keyword = self._extract_query_from_url(url)
                if not keyword:
                    continue

                dt = self._convert_prtime(last_visit_date)
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
