"""ブラウザ履歴データアクセス層 (DAO) の基底モジュール。"""

from abc import ABC, abstractmethod
import logging
from pathlib import Path
import shutil
import tempfile

from personal_knowledge.domain.models import SearchEntry

logger = logging.getLogger(__name__)


class BrowserHistoryDAO(ABC):
    """ブラウザ検索履歴抽出用 DAO の基底クラス。"""

    def __init__(self, history_path: Path | None = None) -> None:
        """BrowserHistoryDAO を初期化する。

        Args:
            history_path: ブラウザ履歴 SQLite ファイルのパス。None の場合はデフォルトパスを使用。
        """
        self._custom_path = history_path

    @property
    @abstractmethod
    def default_history_path(self) -> Path:
        """各ブラウザの標準プロファイルにおける履歴ファイルパス。

        Returns:
            Path: ハードコードされた履歴ファイルパス。
        """
        pass

    @property
    @abstractmethod
    def browser_name(self) -> str:
        """ブラウザの識別子名称。

        Returns:
            str: ブラウザ名 (例: 'chrome', 'edge', 'firefox')。
        """
        pass

    @property
    def target_history_path(self) -> Path:
        """実際にアクセス対象とする履歴ファイルパス。

        Returns:
            Path: 対象履歴ファイルパス。
        """
        if self._custom_path is not None:
            return self._custom_path
        return self.default_history_path

    def fetch_search_entries(self, limit: int = 500) -> list[SearchEntry]:
        """ブラウザの履歴 DB から Google 等の検索クエリ一覧を安全に抽出する。

        ファイルロックを回避するため一時ディレクトリに DB を安全に複製して読み取りを行う。
        失敗時はサイレントに空リストを返却する。

        Args:
            limit: 取得する最大レコード件数。

        Returns:
            list[SearchEntry]: 抽出された検索エントリのリスト。
        """
        target_path = self.target_history_path
        if not target_path.exists():
            logger.debug(f"History file does not exist for {self.browser_name}: {target_path}")
            return []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_db_path = Path(temp_dir) / f"{self.browser_name}_history_temp.db"
                try:
                    shutil.copy2(target_path, temp_db_path)
                except (IOError, OSError, shutil.Error) as copy_err:
                    # ロック競合や権限エラー時は例外を握り潰し（サイレントエラー）、空リストを返す
                    logger.warning(f"Silent skip: Failed to copy {self.browser_name} history DB: {copy_err}")
                    return []

                return self._extract_from_sqlite(temp_db_path, limit=limit)
        except Exception as e:
            # 想定外エラー時もサイレントに処理し、次回の定期実行に委ねる
            logger.warning(f"Silent skip: Unexpected error while reading {self.browser_name} history DB: {e}")
            return []

    @abstractmethod
    def _extract_from_sqlite(self, db_path: Path, limit: int) -> list[SearchEntry]:
        """一時複製された SQLite DB から検索履歴エントリを抽出する。

        Args:
            db_path: 一時コピーされた SQLite ファイルパス。
            limit: 取得最大件数。

        Returns:
            list[SearchEntry]: 抽出結果リスト。

        Raises:
            sqlite3.Error: SQLite 操作エラー。
        """
        pass
