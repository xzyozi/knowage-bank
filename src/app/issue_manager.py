from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import httpx

from app import config
from app.utils.atomic_file import atomic_write_json
from app.utils.logger import logger

load_dotenv()


ISSUE_STATUS_UNPROCESSED = "unprocessed"
ISSUE_STATUS_PROCESSING = "processing"
ISSUE_STATUS_PROCESSED = "processed"
ISSUE_STATUS_FAILED = "failed"
VALID_ISSUE_STATUSES = frozenset(
    {
        ISSUE_STATUS_UNPROCESSED,
        ISSUE_STATUS_PROCESSING,
        ISSUE_STATUS_PROCESSED,
        ISSUE_STATUS_FAILED,
    }
)
ALLOWED_STATUS_TRANSITIONS = {
    ISSUE_STATUS_UNPROCESSED: {ISSUE_STATUS_PROCESSING},
    ISSUE_STATUS_PROCESSING: {ISSUE_STATUS_PROCESSED, ISSUE_STATUS_FAILED},
    ISSUE_STATUS_PROCESSED: set(),
    ISSUE_STATUS_FAILED: set(),
}
ISSUE_RECORD_DEFAULTS: Dict[str, Any] = {
    "number": None,
    "title": "",
    "body": "",
    "state": None,
    "status": ISSUE_STATUS_UNPROCESSED,
    "processed_at": None,
    "article_file": None,
    "article_source_file": None,
    "index_synced": False,
    "attempt_id": None,
    "failed_at": None,
    "failure_reason": None,
}


class IssueManager:
    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            # プロジェクトルート/data/issue_status.json
            self.db_path: str = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "issue_status.json"
            )
        else:
            self.db_path = db_path

        self.github_token = config.GITHUB_TOKEN
        self.github_repo = config.GITHUB_REPOSITORY  # 例: xzyozi/knowage-bank

        self._init_db()

    def _init_db(self) -> None:
        """データベース用JSONファイルの初期化"""
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)

        if not os.path.exists(self.db_path):
            logger.info(f"Initializing new issue status database at {self.db_path}")
            initial_data: Dict[str, Any] = {"last_sync_at": None, "issues": {}}
            self._save_db(initial_data)

    def _load_db(self) -> dict:
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                db_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load issue database: {e}")
            return {"last_sync_at": None, "issues": {}}

        normalized_data, changed = self._normalize_db_data(db_data)
        if changed:
            self._save_db(normalized_data)
        return normalized_data

    def _normalize_db_data(self, db_data: Any) -> tuple[dict, bool]:
        """既存の状態DBを現行スキーマに補完して返す。"""
        if not isinstance(db_data, dict):
            db_data = {}

        normalized_data = dict(db_data)
        changed = "last_sync_at" not in normalized_data
        normalized_data.setdefault("last_sync_at", None)
        raw_issues = normalized_data.get("issues")
        if not isinstance(raw_issues, dict):
            raw_issues = {}
            changed = True

        normalized_issues: dict[str, dict] = {}
        for raw_key, raw_record in raw_issues.items():
            issue_key = str(raw_key)
            normalized_record = self._normalize_issue_record(issue_key, raw_record)
            normalized_issues[issue_key] = normalized_record
            if issue_key != raw_key or normalized_record != raw_record:
                changed = True

        if normalized_data.get("issues") != normalized_issues:
            changed = True
        normalized_data["issues"] = normalized_issues
        return normalized_data, changed

    def _normalize_issue_record(self, issue_key: str, raw_record: Any) -> dict:
        """旧形式のIssueレコードを既定値で補完する。"""
        default_number = int(issue_key) if issue_key.isdigit() else None
        normalized_record = {**ISSUE_RECORD_DEFAULTS, "number": default_number}
        if isinstance(raw_record, dict):
            normalized_record.update(raw_record)

        status = normalized_record["status"]
        if not isinstance(status, str) or status not in VALID_ISSUE_STATUSES:
            logger.warning("Issue #%s has an unknown status; normalizing it to unprocessed.", issue_key)
            normalized_record["status"] = ISSUE_STATUS_UNPROCESSED
        return normalized_record

    @staticmethod
    def _new_issue_record(issue_number: int, title: str, body: str, state: str | None) -> dict:
        return {
            **ISSUE_RECORD_DEFAULTS,
            "number": issue_number,
            "title": title,
            "body": body,
            "state": state,
        }

    def _save_db(self, data: dict) -> None:
        try:
            atomic_write_json(self.db_path, data, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save issue database: {e}")

    def get_headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def sync_issues(self) -> None:
        """GitHub API から直近のIssue差分をフェッチしてローカル状態を更新する"""
        if not self.github_repo:
            logger.error("GITHUB_REPOSITORY environment variable is not set. Sync skipped.")
            return

        db_data = self._load_db()
        last_sync_at = db_data.get("last_sync_at")

        url = f"https://api.github.com/repos/{self.github_repo}/issues"
        params: Dict[str, Any] = {"sort": "updated", "direction": "desc", "state": "all", "per_page": "100"}

        if last_sync_at:
            params["since"] = last_sync_at
            logger.info(f"Fetching issues updated since: {last_sync_at}")
        else:
            logger.info("No previous sync found. Fetching all issues...")

        headers = self.get_headers()
        fetched_issues = []

        # ページネーションループ
        current_url: Optional[str] = url
        try:
            with httpx.Client() as client:
                while current_url:
                    logger.info(f"Requesting GitHub API: {current_url}")
                    response = client.get(current_url, headers=headers, params=params if current_url == url else None)
                    response.raise_for_status()

                    issues = response.json()
                    fetched_issues.extend(issues)

                    # Link ヘッダーを解析して次ページがあるか判定
                    next_url: Optional[str] = None
                    link_header = response.headers.get("Link")
                    if link_header:
                        links = link_header.split(",")
                        for link in links:
                            if 'rel="next"' in link:
                                # <URL> のブラケットをトリムして取得
                                next_url = (
                                    link.substring_between("<", ">")
                                    if hasattr(link, "substring_between")
                                    else link.split(";")[0].strip("<> ")
                                )
                                break
                    current_url = next_url
        except Exception as e:
            logger.error(f"Error occurred during GitHub API fetch: {e}")
            return

        logger.info(f"Fetched {len(fetched_issues)} issues from GitHub.")

        # ローカル状態DBの更新
        new_sync_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        issues_dict = db_data.get("issues", {})

        for issue in fetched_issues:
            # PRもGitHub APIではIssueとして返ってくるため、PRは除外する
            if "pull_request" in issue:
                continue

            issue_num = str(issue.get("number"))
            title = issue.get("title")
            body = issue.get("body", "")
            state = issue.get("state")

            if issue_num in issues_dict:
                # 既存Issueの更新（内容やタイトルの変更）
                issues_dict[issue_num]["title"] = title
                issues_dict[issue_num]["body"] = body
                issues_dict[issue_num]["state"] = state
                logger.debug(f"Updated existing local issue #{issue_num}: {title}")
            else:
                # 新規Issueの登録
                issues_dict[issue_num] = self._new_issue_record(int(issue_num), title, body, state)
                logger.info(f"Registered new local issue #{issue_num}: {title}")

        db_data["last_sync_at"] = new_sync_time
        db_data["issues"] = issues_dict
        self._save_db(db_data)
        logger.info(f"Sync complete. last_sync_at updated to {new_sync_time}")

    def get_next_unprocessed_issue(self) -> dict | None:
        """未処理(unprocessed)かつ最も古い（Issue番号が最小の）Issueを取得する"""
        db_data = self._load_db()
        issues = db_data.get("issues", {})

        unprocessed_list = [issue for issue in issues.values() if issue.get("status") == "unprocessed"]

        if not unprocessed_list:
            return None

        # Issue番号順（昇順）にソートして最古のものを返す
        unprocessed_list.sort(key=lambda x: x.get("number"))
        return unprocessed_list[0]

    def update_issue_status(
        self,
        issue_number: int,
        status: str,
        article_file: Optional[str] = None,
        article_source_file: Optional[str] = None,
        index_synced: Optional[bool] = None,
        attempt_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> bool:
        """許可された状態遷移と成果物・失敗情報を保存する。"""
        db_data = self._load_db()
        issues = db_data["issues"]
        issue_key = str(issue_number)

        if issue_key not in issues:
            logger.error(f"Issue #{issue_number} not found in database. Status update failed.")
            return False

        record = issues[issue_key]
        current_status = record["status"]
        if status not in VALID_ISSUE_STATUSES:
            logger.error("Rejected invalid status '%s' for Issue #%s.", status, issue_number)
            return False
        if status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
            logger.warning(
                "Rejected status transition for Issue #%s: %s -> %s.",
                issue_number,
                current_status,
                status,
            )
            return False

        record["status"] = status
        if attempt_id is not None:
            record["attempt_id"] = attempt_id
        if article_source_file is not None:
            record["article_source_file"] = article_source_file
        if index_synced is not None:
            record["index_synced"] = index_synced
        if article_file is not None:
            # HTML自体は先行段階で保存済みの場合があるため、失敗時も成果物情報を保持する。
            record["article_file"] = article_file

        if status == ISSUE_STATUS_PROCESSED:
            record["processed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            record["index_synced"] = True if index_synced is None else index_synced
            record["failed_at"] = None
            record["failure_reason"] = None
        elif status == ISSUE_STATUS_FAILED:
            record["failed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            record["failure_reason"] = failure_reason

        self._save_db(db_data)
        logger.info(f"Updated Issue #{issue_number} status to '{status}'")
        return True
