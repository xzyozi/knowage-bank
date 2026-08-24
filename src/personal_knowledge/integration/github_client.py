"""GitHub Issue をタスクキューとして操作する API クライアントモジュール。"""

import logging
import os
from typing import Any

import httpx

from personal_knowledge.integration.base_issue_client import BaseIssueClient

logger = logging.getLogger(__name__)


class GitHubIssueClient(BaseIssueClient):
    """GitHub API を通じて Issue の取得・起票・コメント追記を行うクライアントクラス。"""

    def __init__(
        self,
        repo: str | None = None,
        token: str | None = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        """GitHubIssueClient を初期化する。

        Args:
            repo: 'owner/repo' 形式のリポジトリ名。None の場合は環境変数 GITHUB_REPOSITORY を参照。
            token: GitHub Personal Access Token。None の場合は環境変数 GITHUB_TOKEN を参照。
            base_url: GitHub API のベース URL。
        """
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.base_url = base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        """リポジトリとトークンが正しく設定されているか確認する。"""
        return bool(self.repo)

    def _get_headers(self) -> dict[str, str]:
        """リクエスト用ヘッダーを構築する。"""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_open_issues(self) -> list[dict[str, Any]]:
        """Open 状態の Issue 一覧を取得し、コメントも含めて返す。

        Returns:
            list[dict[str, Any]]: Issue 辞書のリスト。
        """
        if not self.is_configured:
            logger.warning("GitHub repository is not configured. Returning empty open issues.")
            return []

        url = f"{self.base_url}/repos/{self.repo}/issues"
        params: dict[str, str | int] = {"state": "open", "per_page": 100}

        try:
            with httpx.Client() as client:
                resp = client.get(url, headers=self._get_headers(), params=params)
                resp.raise_for_status()
                raw_issues = resp.json()

                open_issues: list[dict[str, Any]] = []
                for item in raw_issues:
                    # PR を除外
                    if "pull_request" in item:
                        continue

                    number = item.get("number")
                    comments_list = self._fetch_issue_comments(client, number) if number else []
                    open_issues.append(
                        {
                            "number": number,
                            "title": item.get("title", ""),
                            "body": item.get("body", "") or "",
                            "updated_at": item.get("updated_at", ""),
                            "comments": comments_list,
                        }
                    )
                return open_issues
        except Exception as e:
            logger.error(f"Failed to fetch open issues from GitHub: {e}")
            return []

    def _fetch_issue_comments(self, client: httpx.Client, issue_number: int) -> list[str]:
        """特定の Issue のコメント本文一覧を取得する。"""
        url = f"{self.base_url}/repos/{self.repo}/issues/{issue_number}/comments"
        try:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            comments = resp.json()
            return [c.get("body", "") for c in comments if isinstance(c, dict) and c.get("body")]
        except Exception as e:
            logger.debug(f"Failed to fetch comments for Issue #{issue_number}: {e}")
            return []

    def create_issue(self, title: str, body: str) -> int | None:
        """新しい Issue を起票する。

        Args:
            title: Issue タイトル。
            body: Issue 本文。

        Returns:
            int | None: 起票された Issue 番号。失敗時は None。
        """
        if not self.is_configured:
            logger.warning("GitHub repository is not configured. Cannot create issue.")
            return None

        url = f"{self.base_url}/repos/{self.repo}/issues"
        payload = {"title": title, "body": body}

        try:
            with httpx.Client() as client:
                resp = client.post(url, headers=self._get_headers(), json=payload)
                resp.raise_for_status()
                data = resp.json()
                issue_number = data.get("number")
                logger.info(f"Created new GitHub Issue #{issue_number}: {title}")
                return int(issue_number) if issue_number else None
        except Exception as e:
            logger.error(f"Failed to create GitHub Issue '{title}': {e}")
            return None

    def add_comment(self, issue_number: int, comment_body: str) -> bool:
        """既存の Issue にコメントを追記する。

        Args:
            issue_number: 対象 Issue 番号。
            comment_body: コメント本文。

        Returns:
            bool: 成功時は True、失敗時は False。
        """
        if not self.is_configured:
            logger.warning("GitHub repository is not configured. Cannot add comment.")
            return False

        url = f"{self.base_url}/repos/{self.repo}/issues/{issue_number}/comments"
        payload = {"body": comment_body}

        try:
            with httpx.Client() as client:
                resp = client.post(url, headers=self._get_headers(), json=payload)
                resp.raise_for_status()
                logger.info(f"Added comment to GitHub Issue #{issue_number}")
                return True
        except Exception as e:
            logger.error(f"Failed to add comment to Issue #{issue_number}: {e}")
            return False

    def close_issue(self, issue_number: int) -> bool:
        """Issue を Closed に更新する。

        Args:
            issue_number: 対象 Issue 番号。

        Returns:
            bool: 成功時は True、失敗時は False。
        """
        if not self.is_configured:
            return False

        url = f"{self.base_url}/repos/{self.repo}/issues/{issue_number}"
        payload = {"state": "closed"}

        try:
            with httpx.Client() as client:
                resp = client.patch(url, headers=self._get_headers(), json=payload)
                resp.raise_for_status()
                logger.info(f"Closed GitHub Issue #{issue_number}")
                return True
        except Exception as e:
            logger.error(f"Failed to close Issue #{issue_number}: {e}")
            return False
