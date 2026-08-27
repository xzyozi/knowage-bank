"""検索履歴の流れを模擬（シミュレート）し、実際に選ばれるナレッジ・クエリを分かりやすく出力するスクリプト。"""

from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import sys
from typing import Any

# src/ をモジュール検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personal_knowledge.dao.base_dao import BrowserHistoryDAO
from personal_knowledge.domain.models import SearchEntry, SearchSession
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

    # シナリオ1: Python Dataclass の調査 (既存Issue #101 とマッチして選ばれる想定)
    t1 = now - timedelta(hours=3)
    entries_scene1 = [
        SearchEntry(timestamp=t1, keyword="python dataclass 使い方", source_browser="chrome"),
        SearchEntry(timestamp=t1 + timedelta(minutes=2), keyword="python dataclass 使い方", source_browser="chrome"),  # 重複排除対象
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

    # シナリオ2: FastAPI 非同期処理の調査 (新規Issueとして選ばれる想定)
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

    # シナリオ3: 単発の検索 (ノイズ/セッション化で選ばれず除外される想定)
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
            "body": "Pythonのdataclassモジュールを使ったデータ構造定義とフィールドカスタマイズについての調査ノート。post_initやfield default_factoryの使い方。",
            "comments": [],
        }
    ]


def run_simulation() -> None:
    """検索履歴処理のパイプラインシミュレーションを実行する。"""
    logger.info("=" * 80)
    logger.info("🔍 【STEP 1】 収集された全検索ログ (ブラウザ履歴から読み込まれた生ログ)")
    logger.info("=" * 80)
    mock_entries = create_sample_search_history()
    for idx, entry in enumerate(mock_entries, 1):
        logger.info(
            f"  Raw Entry #{idx:02d} | [{entry.timestamp.strftime('%H:%M:%S')}] "
            f"[{entry.source_browser:7s}] {entry.keyword}"
        )

    mock_issues = create_sample_open_issues()
    logger.info("\n" + "=" * 80)
    logger.info("📚 【STEP 2] 照合対象となる既存のナレッジ (Open Issues)")
    logger.info("=" * 80)
    for issue in mock_issues:
        logger.info(f"  Existing Issue #{issue['number']}: {issue['title']}")

    # サービス構築
    mock_dao = MockHistoryDAO(mock_entries)
    service = PersonalKnowledgeService(
        daos=[mock_dao],
        issue_client=LocalFileIssueClient(),
    )

    # ステップ実行で途中経過も取得
    deduped_entries, sessions = service.process_entries_to_sessions(mock_entries)
    result = service.run_pipeline(dry_run=True, mock_open_issues=mock_issues)

    # 除外されたログの分析
    deduped_set = {(e.timestamp, e.keyword) for e in deduped_entries}
    session_queries_set = {q for s in sessions for q in s.queries}

    logger.info("\n" + "=" * 80)
    logger.info("🚫 【STEP 3】 採択されなかった (除外された) 検索ログと理由")
    logger.info("=" * 80)
    for entry in mock_entries:
        if (entry.timestamp, entry.keyword) not in deduped_set:
            logger.info(
                f"  ❌ [重複除外]    「{entry.keyword}」 ({entry.timestamp.strftime('%H:%M:%S')})\n"
                f"       └ 理由: 5分以内の同一クエリ重複のためマージ"
            )
        elif entry.keyword not in session_queries_set:
            logger.info(
                f"  ❌ [ノイズ除外]  「{entry.keyword}」 ({entry.timestamp.strftime('%H:%M:%S')})\n"
                f"       └ 理由: 連続した技術調査セッションを満たさない単発ログ (最小2件未満)"
            )

    logger.info("\n" + "=" * 80)
    logger.info("🎯 【STEP 4】 実際にナレッジ/Issueとして「選ばれた」もの (選定結果)")
    logger.info("=" * 80)

    for idx, (session, decision) in enumerate(zip(sessions, result.decisions), 1):
        logger.info(f"\n[選出ナレッジ #{idx}] --------------------------------------------------")
        
        if decision.action == "create_issue":
            logger.info("  📌 決定アクション:   【✨ 新規Issueとして選出】")
            logger.info(f"  🏷️  生成タイトル:     {decision.title}")
            logger.info("  💡 選定理由:         既存のどのIssueとも一致しない新しい技術トピックのため新規起票")
        else:
            logger.info("  📌 決定アクション:   【📝 既存Issueへのコメント追記として選出】")
            logger.info(f"  🏷️  対象Issue:        #{decision.target_issue_number}")
            logger.info(f"  📊 語彙類似度スコア: {decision.similarity_score:.4f} (閾値 {service.router.similarity_threshold} 以上)")
            logger.info("  💡 選定理由:         既存Issueトピックと類似度が高いため、関連ナレッジとして追記統合")

        logger.info("\n  🔍 採用・選定された検索クエリ一覧:")
        for q_idx, q in enumerate(session.queries, 1):
            logger.info(f"      {q_idx}. {q}")

        logger.info("\n  📄 生成されるナレッジ本文 (プレビュー):")
        body_lines = decision.body.strip().split("\n")
        for line in body_lines:
            logger.info(f"      {line}")

    logger.info("\n" + "=" * 80)
    logger.info("📊 パイプライン統計サマリー")
    logger.info("=" * 80)
    logger.info(f"  ・全取得検索ログ数:   {result.raw_entries_count} 件")
    logger.info(f"  ・重複排除後ログ数:   {result.deduped_entries_count} 件")
    logger.info(f"  ・選定されたセッション: {result.sessions_count} 件")
    logger.info(f"  ・新規Issue作成判定:  {sum(1 for d in result.decisions if d.action == 'create_issue')} 件")
    logger.info(f"  ・既存Issue追記判定:  {sum(1 for d in result.decisions if d.action == 'add_comment')} 件")
    logger.info("\n✅ シミュレーション完了: Issueへの書き込みは一切行われていません (dry_run)。")


if __name__ == "__main__":
    run_simulation()
