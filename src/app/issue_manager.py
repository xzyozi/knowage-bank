import os
import json
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv
from app.utils.logger import logger
from app import config

load_dotenv()

class IssueManager:
    def __init__(self, db_path: str = None) -> None:
        if db_path is None:
            # プロジェクトルート/data/issue_status.json
            self.db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "issue_status.json"
            )
        else:
            self.db_path = db_path
            
        self.github_token = config.GITHUB_TOKEN
        self.github_repo = config.GITHUB_REPOSITORY # 例: xzyozi/knowage-bank
        
        self._init_db()

    def _init_db(self) -> None:
        """データベース用JSONファイルの初期化"""
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        
        if not os.path.exists(self.db_path):
            logger.info(f"Initializing new issue status database at {self.db_path}")
            initial_data = {
                "last_sync_at": None,
                "issues": {}
            }
            self._save_db(initial_data)

    def _load_db(self) -> dict:
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load issue database: {e}")
            return {"last_sync_at": None, "issues": {}}

    def _save_db(self, data: dict) -> None:
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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
        params = {
            "sort": "updated",
            "direction": "desc",
            "state": "all",
            "per_page": 100
        }
        
        if last_sync_at:
            params["since"] = last_sync_at
            logger.info(f"Fetching issues updated since: {last_sync_at}")
        else:
            logger.info("No previous sync found. Fetching all issues...")

        headers = self.get_headers()
        fetched_issues = []
        
        # ページネーションループ
        current_url = url
        try:
            with httpx.Client() as client:
                while current_url:
                    logger.info(f"Requesting GitHub API: {current_url}")
                    response = client.get(current_url, headers=headers, params=params if current_url == url else None)
                    response.raise_for_status()
                    
                    issues = response.json()
                    fetched_issues.extend(issues)
                    
                    # Link ヘッダーを解析して次ページがあるか判定
                    current_url = None
                    link_header = response.headers.get("Link")
                    if link_header:
                        links = link_header.split(",")
                        for link in links:
                            if 'rel="next"' in link:
                                # <URL> のブラケットをトリムして取得
                                current_url = link.substring_between("<", ">") if hasattr(link, "substring_between") else link.split(";")[0].strip("<> ")
                                break
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
                issues_dict[issue_num] = {
                    "number": int(issue_num),
                    "title": title,
                    "body": body,
                    "state": state,
                    "status": "unprocessed",
                    "processed_at": None,
                    "article_file": None
                }
                logger.info(f"Registered new local issue #{issue_num}: {title}")

        db_data["last_sync_at"] = new_sync_time
        db_data["issues"] = issues_dict
        self._save_db(db_data)
        logger.info(f"Sync complete. last_sync_at updated to {new_sync_time}")

    def get_next_unprocessed_issue(self) -> dict | None:
        """未処理(unprocessed)かつ最も古い（Issue番号が最小の）Issueを取得する"""
        db_data = self._load_db()
        issues = db_data.get("issues", {})
        
        unprocessed_list = [
            issue for issue in issues.values() 
            if issue.get("status") == "unprocessed"
        ]
        
        if not unprocessed_list:
            return None
            
        # Issue番号順（昇順）にソートして最古のものを返す
        unprocessed_list.sort(key=lambda x: x.get("number"))
        return unprocessed_list[0]

    def update_issue_status(self, issue_number: int, status: str, article_file: str = None) -> None:
        """特定のIssueの処理ステータスを更新する"""
        db_data = self._load_db()
        issues = db_data.get("issues", {})
        issue_key = str(issue_number)
        
        if issue_key in issues:
            issues[issue_key]["status"] = status
            if status == "processed":
                issues[issue_key]["processed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if article_file:
                    issues[issue_key]["article_file"] = article_file
            
            db_data["issues"] = issues
            self._save_db(db_data)
            logger.info(f"Updated Issue #{issue_number} status to '{status}'")
        else:
            logger.error(f"Issue #{issue_number} not found in database. Status update failed.")
