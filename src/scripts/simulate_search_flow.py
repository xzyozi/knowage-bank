"""検索履歴の流れを模擬（シミュレート）し、Issue作成なしでパイプライン動作を確認するスクリプト。"""

from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import sys
from typing import Any

# src/ をモジュール検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personal_knowledge.dao.base_dao import BrowserHistoryDAO
from personal_knowledge.domain.models import SearchEntry
from personal_knowledge.integration.local_file_client import LocalFileIssueClient
from personal_knowledge.service import PersonalKnowledgeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("simulate_search_flow")

class MockHistoryDAO(BrowserHistoryDAO):
    """シミュレーション用モック DAO。"""

    def __init__(self, mock_entries: list[SearchEntry], name: str = "MockBrowser") -> None:
        super().__init__()
        self.mock_entries = mock_entries
        self._name = name

    @property
    def default_history_path(self) -> Path:
        return Path("/dev/null")

    @property
    def browser_name(self) -> str:
        return self._name

    def _extract_from_sqlite(self, db_path: Path, limit: int) -> list[SearchEntry]:
        return self.mock_entries

    def fetch_search_entries(self, limit: int = 500) -> list[SearchEntry]:
        return self.mock_entries


def create_sample_search_history() -> list[SearchEntry]:
    """シミュレーション用のサンプル検索履歴データを生成する。"""
    now = datetime.now(timezone.utc)

    # シナリオ1: Python Dataclass の調査 (10分間にわたる連続検索)
    t1 = now - timedelta(hours=2)
    entries_scene1 = [
        SearchEntry(timestamp=t1, keyword="python dataclass 使い方", source_browser="chrome"),
        SearchEntry(timestamp=t1 + timedelta(minutes=2), keyword="python dataclass 使い方", source_browser="chrome"),
        SearchEntry(
            timestamp=t1 + timedelta(minutes=4),
            keyword="python dataclass field default_factory",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=t1 + timedelta(minutes=8),
            keyword="python dataclass post_init 例",
            source_browser="edge",
        ),
    ]

    # シナリオ2: FastAPI 非同期処理の調査 (1時間後、別セッション)
    t2 = now - timedelta(hours=1)
    entries_scene2 = [
        SearchEntry(
            timestamp=t2,
            keyword="fastapi async def sync def 違い",
            source_browser="firefox",
        ),
        SearchEntry(
            timestamp=t2 + timedelta(minutes=5),
            keyword="fastapi concurrency threadpool",
            source_browser="firefox",
        ),
        SearchEntry(
            timestamp=t2 + timedelta(minutes=10),
            keyword="fastapi async def performance benchmark",
            source_browser="chrome",
        ),
    ]

    # シナリオ3: 単発の検索 (ノイズ/セッション分割で最小件数未満として除外想定)
    t3 = now - timedelta(minutes=10)
    entries_scene3 = [
        SearchEntry(timestamp=t3, keyword="今日の天気 東京", source_browser="chrome"),
    ]

    return entries_scene1 + entries_scene2 + entries_scene3


def create_sample_open_issues() -> list[dict[str, Any]]:
    """シミュレーション用のサンプル Open Issue リスト (既存Issue) を生成する。"""
    return [
        {
            "number": 101,
            "title": "Python Dataclassの活用と設計パターン",
            "body": "Pythonのdataclassモジュールを使ったデータ構造定義とフィールドカスタマイズについての調査ノート。",
            "comments": [],
        }
    ]


def run_simulation() -> None:
    """検索履歴処理のパイプラインシミュレーションを実行する。"""
    logger.info("=== [STEP 1] サンプル検索履歴データの準備 ===")
    mock_entries = create_sample_search_history()
    for idx, entry in enumerate(mock_entries, 1):
        logger.info(
            f"  Raw Entry #{idx:02d} | [{entry.timestamp.strftime('%H:%M:%S')}] "
            f"({entry.source_browser}) {entry.keyword}"
        )

    mock_issues = create_sample_open_issues()
    logger.info("\n=== [STEP 2] 既存の Open Issue の確認 (マッチング対象) ===")
    for issue in mock_issues:
        logger.info(f"  Existing Issue #{issue['number']}: {issue['title']}")

    mock_dao = MockHistoryDAO(mock_entries)
    service = PersonalKnowledgeService(
        daos=[mock_dao],
        issue_client=LocalFileIssueClient(),
    )

    logger.info("\n=== [STEP 3] パイプライン実行 (dry_run=True, Issue発効なし) ===")
    result = service.run_pipeline(dry_run=True, mock_open_issues=mock_issues)

    logger.info("\n=== [STEP 4] 実行結果サマリー ===")
    logger.info(f"  ・収集生ログ数:       {result.raw_entries_count} 件")
    logger.info(f"  ・重複排除後ログ数:   {result.deduped_entries_count} 件")
    logger.info(f"  ・抽出セッション数:   {result.sessions_count} 件")
    logger.info(f"  ・新規Issue作成判定:  {result.created_issues_count} 件 (dry_runのため未作成)")
    logger.info(f"  ・コメント追記判定:   {result.added_comments_count} 件 (dry_runのため未追記)")

    logger.info("\n=== [STEP 5] セッションごとのルーティング詳細結果 ===")
    for idx, decision in enumerate(result.decisions, 1):
        logger.info(f"\n--- セッション #{idx} 判定結果 ---")
        logger.info(f"  アクション:     {decision.action}")
        logger.info(f"  タイトル/話題:  {decision.title}")
        if decision.target_issue_number:
            logger.info(f"  対象Issue番号:  #{decision.target_issue_number}")
            logger.info(f"  類似度スコア:   {decision.similarity_score:.4f}")
        else:
            logger.info("  対象Issue番号:  なし (新規Issue作成)")
        logger.info("  本文プレビュー:")
        body_lines = decision.body.strip().split("\n")
        for line in body_lines[:5]:
            logger.info(f"    {line}")
        if len(body_lines) > 5:
            logger.info("    ...")

    logger.info("\n✅ シミュレーション完了: Issueへの影響はありませんでした。")


if __name__ == "__main__":
    run_simulation()
