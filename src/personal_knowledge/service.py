"""パーソナル・ナレッジ自動生成システムの全体オーケストレーションサービス。"""

from dataclasses import dataclass
import logging
import os
from typing import Any

from personal_knowledge.dao.base_dao import BrowserHistoryDAO
from personal_knowledge.dao.chromium_dao import ChromiumHistoryDAO
from personal_knowledge.dao.firefox_dao import FirefoxHistoryDAO
from personal_knowledge.domain.analyzer import SessionAnalyzer
from personal_knowledge.domain.deduplicator import SessionDeduplicator
from personal_knowledge.domain.models import SearchEntry, SearchSession
from personal_knowledge.integration.base_issue_client import BaseIssueClient
from personal_knowledge.integration.github_client import GitHubIssueClient
from personal_knowledge.integration.issue_router import IssueRouter, RoutingDecision
from personal_knowledge.integration.local_file_client import LocalFileIssueClient

logger = logging.getLogger(__name__)


@dataclass
class PipelineExecutionResult:
    """パイプライン実行結果サマリー。

    Attributes:
        raw_entries_count: 収集された生検索ログ総件数。
        deduped_entries_count: 重複排除後の検索ログ件数。
        sessions_count: 抽出されたセッション件数。
        created_issues_count: 新規起票された Issue 件数。
        added_comments_count: コメント追記された件数。
        decisions: 各セッションのルーティング判定結果一覧。
    """

    raw_entries_count: int
    deduped_entries_count: int
    sessions_count: int
    created_issues_count: int
    added_comments_count: int
    decisions: list[RoutingDecision]


class PersonalKnowledgeService:
    """複数ブラウザの履歴収集からセッション解析・Issueルーティングまでを自律実行するサービスクラス。"""

    def __init__(
        self,
        daos: list[BrowserHistoryDAO] | None = None,
        deduplicator: SessionDeduplicator | None = None,
        analyzer: SessionAnalyzer | None = None,
        router: IssueRouter | None = None,
        issue_client: BaseIssueClient | None = None,
        github_client: BaseIssueClient | None = None,
    ) -> None:
        """PersonalKnowledgeService を初期化する。

        Args:
            daos: ブラウザ DAO インスタンスのリスト。None の場合は標準の Chrome, Edge, Firefox DAO を使用。
            deduplicator: 重複排除モジュール。None の場合はデフォルト設定を使用。
            analyzer: セッション解析モジュール。None の場合はデフォルト設定を使用。
            router: ルーティング判定モジュール。None の場合はデフォルト設定を使用。
            issue_client: Issue/ナレッジ格納クライアント。None の場合は環境変数に応じて GitHubIssueClient または LocalFileIssueClient を選択。
            github_client: 旧互換用エイリアス。issue_client が未指定の場合に使用。
        """
        self.daos = daos or [
            ChromiumHistoryDAO(browser_type="chrome"),
            ChromiumHistoryDAO(browser_type="edge"),
            FirefoxHistoryDAO(),
        ]
        self.deduplicator = deduplicator or SessionDeduplicator(time_window_seconds=300)
        self.analyzer = analyzer or SessionAnalyzer(session_gap_seconds=1800, min_queries=2)
        self.router = router or IssueRouter(similarity_threshold=0.3)

        client = issue_client or github_client
        if client is None:
            if os.environ.get("GITHUB_REPOSITORY"):
                client = GitHubIssueClient()
            else:
                client = LocalFileIssueClient()

        self.issue_client: BaseIssueClient = client
        # 互換性のためのエイリアス
        self.github_client = client

    def collect_raw_entries(self) -> list[SearchEntry]:
        """全対象ブラウザから検索ログを収集して合算する。

        Returns:
            list[SearchEntry]: 全ブラウザの検索エントリ合算リスト。
        """
        all_entries: list[SearchEntry] = []
        for dao in self.daos:
            entries = dao.fetch_search_entries()
            logger.info(f"Fetched {len(entries)} entries from {dao.browser_name}")
            all_entries.extend(entries)
        return all_entries

    def process_entries_to_sessions(
        self, raw_entries: list[SearchEntry]
    ) -> tuple[list[SearchEntry], list[SearchSession]]:
        """生エントリから重複排除およびセッション分割を実行する。

        Args:
            raw_entries: 生検索エントリ一覧。

        Returns:
            tuple[list[SearchEntry], list[SearchSession]]: (重複排除済みエントリ, 抽出セッション群)。
        """
        deduped = self.deduplicator.deduplicate(raw_entries)
        sessions = self.analyzer.analyze_sessions(deduped)
        return deduped, sessions

    def run_pipeline(
        self,
        dry_run: bool = False,
        mock_open_issues: list[dict[str, Any]] | None = None,
    ) -> PipelineExecutionResult:
        """収集からセッション解析、Issue ルーティングまでの一連のパイプラインを実行する。

        Args:
            dry_run: True の場合は Issue への起票・コメント追記を行わず判定のみ返す。
            mock_open_issues: テスト用のモック Open Issue リスト。

        Returns:
            PipelineExecutionResult: パイプライン実行結果。
        """
        raw_entries = self.collect_raw_entries()
        deduped, sessions = self.process_entries_to_sessions(raw_entries)

        open_issues = (
            mock_open_issues
            if mock_open_issues is not None
            else self.issue_client.get_open_issues()
        )

        decisions: list[RoutingDecision] = []
        created_count = 0
        commented_count = 0

        for session in sessions:
            decision = self.router.evaluate_routing(session, open_issues)
            decisions.append(decision)

            if not dry_run:
                if decision.action == "add_comment" and decision.target_issue_number:
                    success = self.issue_client.add_comment(
                        decision.target_issue_number, decision.body
                    )
                    if success:
                        commented_count += 1
                elif decision.action == "create_issue":
                    new_number = self.issue_client.create_issue(decision.title, decision.body)
                    if new_number:
                        created_count += 1
                        # 次のセッション判定用に open_issues をローカル更新
                        open_issues.append(
                            {
                                "number": new_number,
                                "title": decision.title,
                                "body": decision.body,
                                "comments": [],
                            }
                        )

        return PipelineExecutionResult(
            raw_entries_count=len(raw_entries),
            deduped_entries_count=len(deduped),
            sessions_count=len(sessions),
            created_issues_count=created_count,
            added_comments_count=commented_count,
            decisions=decisions,
        )
