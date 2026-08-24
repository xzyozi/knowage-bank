"""GitHub 非依存でローカル JSON ファイルまたはメモリ上に Issue / ナレッジ項目を保存・管理するクライアントモジュール。"""

import json
import logging
from pathlib import Path
from typing import Any

from personal_knowledge.integration.base_issue_client import BaseIssueClient

logger = logging.getLogger(__name__)


class LocalFileIssueClient(BaseIssueClient):
    """ローカルファイル (JSON) またはメモリ上で Issue データ群を保持・管理するクライアントクラス。"""

    def __init__(self, storage_path: Path | str | None = None) -> None:
        """LocalFileIssueClient を初期化する。

        Args:
            storage_path: JSON データの保存先パス。None の場合はデフォルト `data/personal_knowledge_issues.json` を使用。
        """
        if storage_path is None:
            self.storage_path: Path | None = Path("data/personal_knowledge_issues.json")
        elif storage_path == "":
            self.storage_path = None
        else:
            self.storage_path = Path(storage_path)

        self._issues: list[dict[str, Any]] = []
        self._next_id: int = 1
        self._load_data()

    @property
    def is_configured(self) -> bool:
        """ローカルクライアントは常に利用可能。"""
        return True

    def _load_data(self) -> None:
        """ストレージファイルから Issue データを読み込む。"""
        if not self.storage_path or not self.storage_path.exists():
            self._issues = []
            self._next_id = 1
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._issues = data
                    max_num = max((i.get("number", 0) for i in self._issues if isinstance(i, dict)), default=0)
                    self._next_id = max_num + 1
                else:
                    self._issues = []
                    self._next_id = 1
        except Exception as e:
            logger.error(f"Failed to load issues from local file {self.storage_path}: {e}")
            self._issues = []
            self._next_id = 1

    def _save_data(self) -> None:
        """メモリ上の Issue データをストレージファイルへ保存する。"""
        if not self.storage_path:
            return

        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._issues, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save issues to local file {self.storage_path}: {e}")

    def get_open_issues(self) -> list[dict[str, Any]]:
        """Open 状態の Issue 一覧を取得する。

        Returns:
            list[dict[str, Any]]: Open 状態の Issue リスト。
        """
        open_list: list[dict[str, Any]] = []
        for item in self._issues:
            if item.get("state", "open") == "open":
                open_list.append(
                    {
                        "number": item.get("number"),
                        "title": item.get("title", ""),
                        "body": item.get("body", ""),
                        "comments": item.get("comments", []),
                    }
                )
        return open_list

    def create_issue(self, title: str, body: str) -> int | None:
        """新しい Issue を作成する。

        Args:
            title: Issue タイトル。
            body: Issue 本文。

        Returns:
            int | None: 起票された Issue 番号。
        """
        issue_number = self._next_id
        self._next_id += 1

        new_issue = {
            "number": issue_number,
            "title": title,
            "body": body,
            "state": "open",
            "comments": [],
        }
        self._issues.append(new_issue)
        self._save_data()
        logger.info(f"Created local issue #{issue_number}: {title}")
        return issue_number

    def add_comment(self, issue_number: int, comment_body: str) -> bool:
        """既存の Issue にコメントを追記する。

        Args:
            issue_number: 対象 Issue 番号。
            comment_body: コメント本文。

        Returns:
            bool: 成功時は True。
        """
        for item in self._issues:
            if item.get("number") == issue_number:
                if "comments" not in item or not isinstance(item["comments"], list):
                    item["comments"] = []
                item["comments"].append(comment_body)
                self._save_data()
                logger.info(f"Added comment to local issue #{issue_number}")
                return True
        logger.warning(f"Local issue #{issue_number} not found for adding comment.")
        return False

    def close_issue(self, issue_number: int) -> bool:
        """Issue をクローズ状態にする。

        Args:
            issue_number: 対象 Issue 番号。

        Returns:
            bool: 成功時は True。
        """
        for item in self._issues:
            if item.get("number") == issue_number:
                item["state"] = "closed"
                self._save_data()
                logger.info(f"Closed local issue #{issue_number}")
                return True
        return False
