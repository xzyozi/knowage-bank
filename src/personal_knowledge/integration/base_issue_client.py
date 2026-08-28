"""Issue / ナレッジ保存先の抽象クライアントインターフェースモジュール。"""

from abc import ABC, abstractmethod
from typing import Any


class BaseIssueClient(ABC):
    """Issue または ナレッジ格納先に対する抽象クライアント基底クラス。"""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """クライアントが正しく設定されているか確認する。"""
        ...

    @abstractmethod
    def get_open_issues(self) -> list[dict[str, Any]]:
        """Open 状態の Issue (またはアクティブなナレッジ項目) 一覧を取得する。

        Returns:
            list[dict[str, Any]]: {'number': int, 'title': str, 'body': str, 'comments': list[str]} 形式のリスト。
        """
        ...

    @abstractmethod
    def create_issue(self, title: str, body: str) -> int | None:
        """新しい Issue (またはナレッジ項目) を作成する。

        Args:
            title: タイトル。
            body: 本文。

        Returns:
            int | None: 発行された Issue ID/番号。失敗時は None。
        """
        ...

    @abstractmethod
    def add_comment(self, issue_number: int, comment_body: str) -> bool:
        """既存の Issue (またはナレッジ項目) にコメントを追記する。

        Args:
            issue_number: 対象 Issue 番号。
            comment_body: 追記するコメント本文。

        Returns:
            bool: 成功時は True、失敗時は False。
        """
        ...

    @abstractmethod
    def close_issue(self, issue_number: int) -> bool:
        """Issue (またはナレッジ項目) をクローズ・完了状態にする。

        Args:
            issue_number: 対象 Issue 番号。

        Returns:
            bool: 成功時は True、失敗時は False。
        """
        ...
