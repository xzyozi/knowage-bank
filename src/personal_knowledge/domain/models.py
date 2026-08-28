"""パーソナル・ナレッジ自動生成システムのコアデータモデル (DTO)。"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SearchEntry:
    """ブラウザから抽出された生の検索クエリDTO。

    Attributes:
        timestamp: 検索が実行された日時 (UTC)。
        keyword: 検索キーワード文字列。
        source_browser: 取得元ブラウザ種別 (例: 'chrome', 'edge', 'firefox')。
    """

    timestamp: datetime
    keyword: str
    source_browser: str


@dataclass
class SearchSession:
    """意味付けされた技術調査セッションDTO。

    Attributes:
        start_time: セッション内の最古クエリ検索日時 (UTC)。
        end_time: セッション内の最新クエリ検索日時 (UTC)。
        queries: セッションに含まれる検索キーワードのリスト。
        source_browsers: セッションに関与したブラウザ識別子リスト。
    """

    start_time: datetime
    end_time: datetime
    queries: list[str]
    source_browsers: list[str] = field(default_factory=list)
