"""パーソナル・ナレッジ検索履歴収集・セッション解析・Issueルーティング実行スクリプト。"""

import argparse
import json
import logging
import os
import sys

# src/ をモジュール検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

from personal_knowledge.integration.github_client import GitHubIssueClient
from personal_knowledge.integration.local_file_client import LocalFileIssueClient
from personal_knowledge.service import PersonalKnowledgeService

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("personal_knowledge_runner")


def main() -> None:
    """CLI エントリーポイント。"""
    parser = argparse.ArgumentParser(
        description="複数ブラウザからの検索履歴収集・セッション解析・Issueルーティング自律実行スクリプト"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Issue への起票やコメント追記を行わず、抽出・ルーティング判定結果のみを表示する",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="実行結果を JSON 形式で標準出力に出力する",
    )
    parser.add_argument(
        "--backend",
        choices=["github", "local"],
        default=None,
        help="保存先ストレージバックエンド ('github' または 'local')。未指定の場合は環境変数から自動判定。",
    )
    args = parser.parse_args()

    issue_client = None
    if args.backend == "github":
        issue_client = GitHubIssueClient()
    elif args.backend == "local":
        issue_client = LocalFileIssueClient()

    service = PersonalKnowledgeService(issue_client=issue_client)
    logger.info(
        f"Starting Personal Knowledge Collection & Routing pipeline (backend: {service.issue_client.__class__.__name__})..."
    )
    result = service.run_pipeline(dry_run=args.dry_run)

    summary = {
        "raw_entries_count": result.raw_entries_count,
        "deduped_entries_count": result.deduped_entries_count,
        "sessions_count": result.sessions_count,
        "created_issues_count": result.created_issues_count,
        "added_comments_count": result.added_comments_count,
        "decisions": [
            {
                "action": d.action,
                "target_issue_number": d.target_issue_number,
                "similarity_score": round(d.similarity_score, 4),
                "title": d.title,
            }
            for d in result.decisions
        ],
    }

    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        logger.info(
            f"Pipeline completed: Raw={result.raw_entries_count}, "
            f"Deduped={result.deduped_entries_count}, "
            f"Sessions={result.sessions_count}, "
            f"Created={result.created_issues_count}, "
            f"Commented={result.added_comments_count}"
        )


if __name__ == "__main__":
    main()
