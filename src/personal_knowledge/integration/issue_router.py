"""検索セッションと既存 Open Issue 間の類似度判定およびルーティングモジュール。"""

from dataclasses import dataclass
import re
from typing import Any

from personal_knowledge.domain.models import SearchSession


@dataclass
class RoutingDecision:
    """ルーティング判定結果。

    Attributes:
        action: 'create_issue' (新規起票) または 'add_comment' (コメント追記)。
        target_issue_number: コメント追記先 Issue 番号 (action == 'add_comment' の場合)。
        similarity_score: 最大類似度スコア (0.0 〜 1.0)。
        title: 新規起票時のタイトル。
        body: 起票本文または追記コメント本文。
    """

    action: str
    target_issue_number: int | None
    similarity_score: float
    title: str
    body: str


class IssueRouter:
    """語彙類似度（Overlap / Jaccard 係数）による判定を行い、セッションを適切な Issue にルーティングするクラス。"""

    # ノイズとなる定型メタテキスト・ストップワード
    STOP_WORDS: set[str] = {
        "自動抽出",
        "技術調査",
        "セッション",
        "開始日時",
        "終了日時",
        "検出ブラウザ",
        "検索クエリ一覧",
        "追加の調査セッション",
        "関連の調査",
        "関連クエリ",
        "検出日時",
        "http",
        "https",
        "utc",
        "関連",
        "調査",
    }

    def __init__(self, similarity_threshold: float = 0.3) -> None:
        """IssueRouter を初期化する。

        Args:
            similarity_threshold: コメント追記と判定する語彙類似度の最小閾値 (デフォルト: 0.3)。
        """
        self.similarity_threshold = similarity_threshold

    @classmethod
    def tokenize(cls, text: str) -> set[str]:
        """テキストから英単語、カタカナ語、漢字語、意味のある日本語単語トークン集合を抽出する。

        Args:
            text: 解析対象テキスト。

        Returns:
            set[str]: 語彙トークンのセット。
        """
        if not text:
            return set()

        normalized = text.lower()
        tokens: set[str] = set()

        # 1. 英数字単語 (スネークケース・キャメルケース含む, 長さ 2 以上)
        words = re.findall(r"[a-z0-9_]{2,}", normalized)
        for w in words:
            if w not in cls.STOP_WORDS:
                tokens.add(w)
                # スネークケースの構成要素も追加 (例: wait_for -> wait, for)
                if "_" in w:
                    for sub_w in w.split("_"):
                        if len(sub_w) >= 2 and sub_w not in cls.STOP_WORDS:
                            tokens.add(sub_w)

        # 2. カタカナ単語 (長さ 2 以上)
        katakana_words = re.findall(r"[\u30a1-\u30fa\u30fc]{2,}", text)
        for kw in katakana_words:
            norm_kw = kw.strip().lower()
            if norm_kw not in cls.STOP_WORDS:
                tokens.add(norm_kw)

        # 3. 漢字連続単語 (長さ 2 以上)
        kanji_words = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        for kanji in kanji_words:
            if kanji not in cls.STOP_WORDS:
                tokens.add(kanji)
                # 3文字以上の漢字熟語の場合は2文字部分文字列も追加 (例: 例外伝播 -> 例外, 伝播)
                if len(kanji) >= 3:
                    for i in range(len(kanji) - 1):
                        sub_k = kanji[i : i + 2]
                        if sub_k not in cls.STOP_WORDS:
                            tokens.add(sub_k)

        # 4. 助詞・記号で分割された日本語フレーズ
        phrases = re.split(r"[\s、。,.!?:;（）()\[\]【】\-_/|〜~「」『』\n\r]+", text)
        for phrase in phrases:
            cleaned = phrase.strip().lower()
            if len(cleaned) >= 2 and cleaned not in cls.STOP_WORDS:
                # 記号のみや助詞のみでなければ追加
                if not re.match(r"^[のにはがでをとや]+$", cleaned):
                    tokens.add(cleaned)

        return tokens

    @classmethod
    def calculate_similarity(cls, tokens_session: set[str], tokens_issue: set[str]) -> float:
        """短文のセッションと長文の Issue 本文間の語彙類似度 (Overlap 係数 / Jaccard 包含率) を計算する。

        短文クエリと長文ドキュメント間の比較に適した Szymkiewicz-Simpson (Overlap) 係数を採用。

        Args:
            tokens_session: 検索セッション側の語彙トークン集合。
            tokens_issue: Issue 側の語彙トークン集合。

        Returns:
            float: 類似度スコア (0.0 〜 1.0)。
        """
        if not tokens_session or not tokens_issue:
            return 0.0

        intersection = tokens_session.intersection(tokens_issue)
        if not intersection:
            return 0.0

        # セッション側のトークンがどれだけ Issue 側に含まれているか（包含率）
        coverage = len(intersection) / len(tokens_session)

        # 標準 Jaccard
        jaccard = len(intersection) / len(tokens_session.union(tokens_issue))

        # Overlap 係数
        overlap = len(intersection) / min(len(tokens_session), len(tokens_issue))

        # セッションのトピック合致度を重視したスコア (Coverage と Overlap の最大値)
        return max(coverage, overlap, jaccard)

    @classmethod
    def calculate_jaccard_similarity(cls, tokens_a: set[str], tokens_b: set[str]) -> float:
        """2つのトークン集合間の標準 Jaccard 係数を計算する。

        Args:
            tokens_a: トークン集合 A。
            tokens_b: トークン集合 B。

        Returns:
            float: Jaccard 係数 (0.0 〜 1.0)。
        """
        if not tokens_a or not tokens_b:
            return 0.0
        intersection_len = len(tokens_a.intersection(tokens_b))
        union_len = len(tokens_a.union(tokens_b))
        return intersection_len / union_len if union_len > 0 else 0.0

    def evaluate_routing(self, session: SearchSession, open_issues: list[dict[str, Any]]) -> RoutingDecision:
        """セッションと Open 状態の Issue 群を照合し、起票または追記の決定を行う。

        Args:
            session: 対象の検索セッション。
            open_issues: Open 状態の Issue リスト ({'number': int, 'title': str, 'body': str, 'comments': list[str]})。

        Returns:
            RoutingDecision: 判定結果。
        """
        session_text = " ".join(session.queries)
        session_tokens = self.tokenize(session_text)

        best_score = 0.0
        best_issue_number: int | None = None

        for issue in open_issues:
            issue_number = int(issue.get("number", 0))
            issue_title = str(issue.get("title", ""))
            issue_body = str(issue.get("body", ""))
            comments = issue.get("comments", [])
            comments_text = " ".join(str(c) for c in comments) if isinstance(comments, list) else ""

            combined_issue_text = f"{issue_title} {issue_body} {comments_text}"
            issue_tokens = self.tokenize(combined_issue_text)

            score = self.calculate_similarity(session_tokens, issue_tokens)
            if score > best_score:
                best_score = score
                best_issue_number = issue_number

        first_query = session.queries[0] if session.queries else "技術調査"
        browsers_str = ", ".join(session.source_browsers) if session.source_browsers else "Unknown"

        if best_score >= self.similarity_threshold and best_issue_number is not None:
            # 既存 Issue へのコメント追記
            comment_body = (
                f"### 追加の調査セッション (検出日時: {session.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')})\n\n"
                f"- **検出ブラウザ**: {browsers_str}\n"
                f"- **関連クエリ**:\n"
            )
            for q in session.queries:
                comment_body += f"  - {q}\n"

            return RoutingDecision(
                action="add_comment",
                target_issue_number=best_issue_number,
                similarity_score=best_score,
                title="",
                body=comment_body,
            )

        # 類似度不足による新規 Issue 起票
        title = f"[自動抽出] {first_query} 関連の調査"
        issue_body = (
            f"## 自動抽出された技術調査セッション\n\n"
            f"- **開始日時**: {session.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"- **終了日時**: {session.end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"- **検出ブラウザ**: {browsers_str}\n\n"
            f"### 検索クエリ一覧\n"
        )
        for i, q in enumerate(session.queries, 1):
            issue_body += f"{i}. {q}\n"

        return RoutingDecision(
            action="create_issue",
            target_issue_number=None,
            similarity_score=best_score,
            title=title,
            body=issue_body,
        )
