"""パーソナル・ナレッジ検索履歴収集・セッション解析・Issueルーティング実行スクリプト。"""

import argparse
import json
import logging
import os
import sys
from typing import Literal

# src/ をモジュール検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

from personal_knowledge.domain.analyzer import SessionAnalyzer
from personal_knowledge.domain.deduplicator import SessionDeduplicator
from personal_knowledge.domain.intent_filter import IntentFilter
from personal_knowledge.domain.semantic_clusterer import SemanticClusterer
from personal_knowledge.infrastructure.model_resolver import ModelResolver
from personal_knowledge.integration.base_issue_client import BaseIssueClient
from personal_knowledge.integration.github_client import GitHubIssueClient
from personal_knowledge.integration.issue_router import IssueRouter
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
    parser.add_argument(
        "--no-gemini",
        dest="use_gemini",
        action="store_false",
        help="Gemini AI 意図判定・Embedding結合を無効化し、ルールベースのみで処理を行う場合に使用",
    )
    parser.add_argument(
        "--refresh-models",
        action="store_true",
        help="Geminiの利用可能モデル一覧キャッシュを更新してから実行する",
    )
    parser.set_defaults(use_gemini=True)

    # --- セッション選定チューニング用パラメータ ---
    parser.add_argument(
        "--session-gap-seconds",
        type=int,
        default=1800,
        help="同一セッションとみなす検索間隔の最大秒数 (デフォルト: 1800秒 = 30分)",
    )
    parser.add_argument(
        "--min-queries",
        type=int,
        default=2,
        help="セッションとして採択する最小検索クエリ件数 (デフォルト: 2件)",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.3,
        help="既存Issue追記判定の類似度閾値 0.0〜1.0 (デフォルト: 0.3)",
    )
    parser.add_argument(
        "--dedup-window-seconds",
        type=int,
        default=300,
        help="同一キーワードの重複排除を行う時間ウィンドウ秒数 (デフォルト: 300秒 = 5分)",
    )
    args = parser.parse_args()

    issue_client: BaseIssueClient | None = None
    if args.backend == "github":
        issue_client = GitHubIssueClient()
    elif args.backend == "local":
        issue_client = LocalFileIssueClient()

    model_resolver = ModelResolver()
    if args.use_gemini and args.refresh_models:
        model_resolver.resolve_candidates("generate_content", force_refresh=True)
        model_resolver.resolve_candidates("embed_content", force_refresh=True)

    intent_filter: IntentFilter | Literal[False] = (
        IntentFilter(model_resolver=model_resolver) if args.use_gemini else False
    )
    semantic_clusterer = SemanticClusterer(model_resolver=model_resolver) if args.use_gemini else None

    # カスタム選定パラメータをコンポーネントに反映
    deduplicator = SessionDeduplicator(time_window_seconds=args.dedup_window_seconds)
    analyzer = SessionAnalyzer(session_gap_seconds=args.session_gap_seconds, min_queries=args.min_queries)
    router = IssueRouter(similarity_threshold=args.similarity_threshold)

    service = PersonalKnowledgeService(
        issue_client=issue_client,
        deduplicator=deduplicator,
        analyzer=analyzer,
        router=router,
        intent_filter=intent_filter,
        semantic_clusterer=semantic_clusterer,
        model_resolver=model_resolver,
    )
    logger.info(
        "Starting Personal Knowledge Collection & Routing pipeline "
        f"(backend: {service.issue_client.__class__.__name__}, gemini: {args.use_gemini}, "
        f"session_gap: {args.session_gap_seconds}s, min_queries: {args.min_queries}, "
        f"similarity_threshold: {args.similarity_threshold})..."
    )

    # 収集と解析を実行
    raw_entries = service.collect_raw_entries()
    deduped_entries, sessions = service.process_entries_to_sessions(raw_entries)

    # Issueルーティング
    open_issues = service.issue_client.get_open_issues()
    result = service.run_pipeline(dry_run=args.dry_run, mock_open_issues=open_issues)

    stats = intent_filter.usage_stats if isinstance(intent_filter, IntentFilter) else None
    model_resolution = {}
    for purpose in ("generate_content", "embed_content"):
        resolution = model_resolver.get_resolution(purpose)
        if resolution is not None:
            model_resolution[purpose] = {
                "selected_model": resolution.selected_model,
                "candidate_source": resolution.candidate_source,
                "fallback_count": resolution.fallback_count,
                "fallback_reasons": resolution.fallback_reasons,
                "resolved_at": resolution.resolved_at.isoformat(),
            }

    summary = {
        "raw_entries_count": result.raw_entries_count,
        "deduped_entries_count": result.deduped_entries_count,
        "sessions_count": result.sessions_count,
        "created_issues_count": result.created_issues_count,
        "added_comments_count": result.added_comments_count,
        "model_resolution": model_resolution,
        "decisions": [
            {
                "action": d.action,
                "target_issue_number": d.target_issue_number,
                "similarity_score": round(d.similarity_score, 4),
                "title": d.title,
                "queries": session.queries if idx < len(sessions) else [],
            }
            for idx, (d, session) in enumerate(zip(result.decisions, sessions))
        ],
    }

    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        logger.info("\n" + "=" * 80)
        logger.info("🎯 【採択（選定）されたナレッジ一覧】 実際にナレッジ/Issueとして選ばれたセッション")
        logger.info("=" * 80)

        for idx, (decision, session) in enumerate(zip(result.decisions, sessions), 1):
            if decision.action == "create_issue":
                logger.info(f"\n[選出ナレッジ #{idx}] 📌 【新規Issueとして選定】: {decision.title}")
            else:
                logger.info(
                    f"\n[選出ナレッジ #{idx}] 📌 【既存Issue #{decision.target_issue_number} への追記として選定】 "
                    f"(類似度: {decision.similarity_score:.4f})"
                )

            logger.info("   選定キーワード:")
            for q_idx, q in enumerate(session.queries, 1):
                logger.info(f"     {q_idx}. {q}")

        logger.info("\n" + "=" * 80)
        logger.info(
            f"Pipeline completed (dry_run={args.dry_run}): Raw={result.raw_entries_count}, "
            f"Deduped={result.deduped_entries_count}, "
            f"Selected Sessions={result.sessions_count}, "
            f"Created={result.created_issues_count}, "
            f"Commented={result.added_comments_count}"
        )
        if stats:
            logger.info("\n" + "=" * 80)
            logger.info("💡 【Gemini API 使用量・利用制限ステータス (Usage Tracker)】")
            logger.info("=" * 80)
            logger.info(
                f"  ・API呼び出し回数:  {stats.request_count} 回 / 1日上限 1,500 回 (使用率: {stats.request_count / 1500 * 100:.2f}%)"
            )
            logger.info(f"  ・合計消費トークン: {stats.total_tokens} tokens (1分あたり上限 1,000,000 tokens)")
            logger.info("  ・概算コスト:       $0.00 (Google GenAI API 無料枠 Free Tier 範囲内)")


if __name__ == "__main__":
    main()
