from datetime import datetime
import json
import os
import re
import subprocess
import sys

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.utils.logger import logger

# ==========================================
# 定数定義
# ==========================================
RECENT_LIMIT = 6

# ==========================================
# 定数・設定の動的ロード
# ==========================================
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "category_config.json")
if not os.path.exists(config_path):
    config_path = "config/category_config.json"

try:
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)
    CLUSTERS = config_data.get("clusters", {})
    CLUSTER_ORDER = config_data.get("cluster_order", [])
except Exception as e:
    logger.error(f"Failed to load category config: {e}")
    CLUSTERS = {}
    CLUSTER_ORDER = []


# ==========================================
# ユーティリティ関数
# ==========================================
def get_creation_date(filepath: str) -> datetime:
    """git log --follow --reverse で最初のコミット日を取得"""
    if not os.path.exists(filepath):
        return datetime.now()

    try:
        # PowerShellやGitのパス解決のため、絶対パス化
        abs_path = os.path.abspath(filepath)
        result = subprocess.run(
            ["git", "log", "--follow", "--reverse", "--format=%aI", "--", abs_path],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.strip().splitlines()
        if lines and lines[0]:
            # ISO 8601 形式のパース（比較用にタイムゾーン情報を除去）
            return datetime.fromisoformat(lines[0]).replace(tzinfo=None)
    except Exception as e:
        logger.warning(f"Failed to get git log for {filepath}: {e}")

    # コミット履歴がない場合はファイルの最終更新日を使用
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime)


def parse_html_metadata(filepath: str) -> dict:
    """記事 HTML からタイトル (h1)、概要 (.lead)、eyebrow などのメタデータを抽出"""
    meta = {"title": "無題の記事", "description": "概要はありません。", "eyebrow": "未分類", "meta_text": ""}

    if not os.path.exists(filepath):
        return meta

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # タイトル (h1) の抽出
        h1_match = re.search(r"<h1>(.*?)</h1>", content, re.DOTALL)
        if h1_match:
            meta["title"] = h1_match.group(1).strip()

        # リード文 (.lead) の抽出
        lead_match = re.search(r'<p class="lead">(.*?)</p>', content, re.DOTALL)
        if lead_match:
            # HTMLタグの除去
            lead_text = re.sub(r"<[^>]+>", "", lead_match.group(1))
            meta["description"] = lead_text.strip()

        # eyebrow の抽出
        eyebrow_match = re.search(r'<p class="eyebrow">(.*?)</p>', content, re.DOTALL)
        if eyebrow_match:
            meta["eyebrow"] = eyebrow_match.group(1).strip()

        # メタテキスト (もしあれば)
        meta_match = re.search(r'<span class="meta">(.*?)</span>', content, re.DOTALL)
        if meta_match:
            meta["meta_text"] = meta_match.group(1).strip()

    except Exception as e:
        logger.error(f"Failed to parse HTML metadata from {filepath}: {e}")

    return meta


def update_article_date(filepath: str, date: datetime) -> None:
    """記事 HTML 内の <time> 要素の日付を更新"""
    if not os.path.exists(filepath):
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        formatted_datetime = date.strftime("%Y-%m-%d")

        # 正規表現による time タグの置換
        # パターン: <p class="article-created"><time datetime="...">作成日: ...</time></p>
        pattern = r'(<p class="article-created"><time datetime=")[^"]*(">[^<]*</time></p>)'
        new_content, count = re.subn(
            pattern,
            lambda m: f'{m.group(1)}{formatted_datetime}">作成日: {date.year}年{date.month}月{date.day}日</time></p>',
            content,
        )

        # 直書きの time 要素用（template用）
        if count == 0:
            pattern_simple = r'(<time datetime=")[^"]*(">[^<]*</time>)'
            new_content, count = re.subn(
                pattern_simple,
                f'\\1{formatted_datetime}">作成日: {date.year}年{date.month}月{date.day}日</time>',
                content,
            )

        if count > 0:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.info(f"Updated date for {os.path.basename(filepath)} to {formatted_datetime}")
    except Exception as e:
        logger.error(f"Failed to update date in {filepath}: {e}")


# ==========================================
# メイン処理
# ==========================================
def main() -> None:
    logger.info("Starting article date synchronization and index generation...")

    articles = []
    articles_dir = os.path.join("public", "articles")
    if not os.path.exists(articles_dir):
        logger.error(f"Articles directory not found at {articles_dir}")
        return

    # HTMLファイル名のリストを自動スキャン (template.htmlは除外)
    html_files = [f for f in os.listdir(articles_dir) if f.endswith(".html") and f != "template.html"]

    # eyebrow（タグ名）からクラスタIDを逆引きするためのマップを作成
    # HTMLエンティティの表記ブレ（&amp; や &gt; など）に対応するため、アンエスケープして正規化
    import html

    eyebrow_to_cluster = {}
    for cl_id, cl_info in CLUSTERS.items():
        raw_eyebrow = cl_info.get("eyebrow", "")
        # 通常テキスト表記
        eyebrow_to_cluster[raw_eyebrow] = cl_id
        # HTMLエンティティ表記
        escaped_eyebrow = html.escape(raw_eyebrow)
        eyebrow_to_cluster[escaped_eyebrow] = cl_id
        # 空白ゆらぎの考慮
        eyebrow_to_cluster[raw_eyebrow.replace(" ", "")] = cl_id
        eyebrow_to_cluster[escaped_eyebrow.replace(" ", "")] = cl_id

    # 各ファイルの更新とデータ取得
    for filename in html_files:
        filepath = os.path.join(articles_dir, filename)

        # 作成日の取得
        date = get_creation_date(filepath)

        # 記事HTML内の日付更新
        update_article_date(filepath, date)

        # メタデータの抽出
        meta = parse_html_metadata(filepath)

        # HTMLのeyebrow（タグ名）からクラスタIDを自動判定
        raw_html_eyebrow = meta.get("eyebrow", "")
        html_eyebrow_key = raw_html_eyebrow.replace(" ", "")

        cluster_id = eyebrow_to_cluster.get(raw_html_eyebrow, eyebrow_to_cluster.get(html_eyebrow_key, None))

        if not cluster_id:
            logger.warning(
                f"File '{filename}' has eyebrow '{raw_html_eyebrow}' which does not match any registered cluster in category_config.json. Skipping."
            )
            continue

        articles.append(
            {
                "filename": filename,
                "slug": os.path.splitext(filename)[0],
                "date": date,
                "cluster_id": cluster_id,
                **meta,
            }
        )

    # 2. 新着記事のHTML生成
    # 作成日降順でソート
    sorted_by_date = sorted(articles, key=lambda x: x["date"], reverse=True)
    recent_articles = sorted_by_date[:RECENT_LIMIT]

    recent_html_parts = []
    for art in recent_articles:
        date_str = art["date"].strftime("%Y-%m-%d")
        display_date = f"{art['date'].year}年{art['date'].month}月{art['date'].day}日"

        card_html = f"""            <a class="article-card" href="articles/{art["filename"]}">
                <p class="card-meta-row">
                    <time class="article-date" datetime="{date_str}">{display_date}</time>
                    <span class="eyebrow">{art["eyebrow"]}</span>
                </p>
                <h4>{art["title"]}</h4>
                <p>{art["description"]}</p>
                <span class="meta">{art["meta_text"]}</span>
            </a>"""
        recent_html_parts.append(card_html)

    recent_html = (
        "\n".join(recent_html_parts)
        if recent_html_parts
        else '            <p class="empty-note">新着記事はまだありません。</p>'
    )

    # 3. ドメイン別・クラスタ別のHTML生成
    # ドメインごとのクラスタ内最新記事の日付（代表日）を格納
    cluster_latest_dates = {}
    epoch_min = datetime(2000, 1, 1)  # Windows の timestamp 制限エラー(1970年以前の負の秒数)回避のため2000年とする
    for cl_id in CLUSTERS.keys():
        cluster_arts = [a for a in articles if a["cluster_id"] == cl_id]
        if cluster_arts:
            cluster_latest_dates[cl_id] = max(a["date"] for a in cluster_arts)
        else:
            # 記事がないクラスタは最古の日付
            cluster_latest_dates[cl_id] = epoch_min

    # ドメインごとにクラスタをソートしてHTML生成
    domains = ["dev", "game", "ai", "infra"]
    domain_html_dict = {d: "" for d in domains}

    for domain in domains:
        # そのドメインに属するクラスタを取得
        domain_clusters = [cl_id for cl_id, info in CLUSTERS.items() if info["domain"] == domain]

        # 代表日の降順でクラスタをソート（日付が未設定/最古のものは後ろに、同日の場合は CLUSTER_ORDER 順）
        def cluster_sort_key(cl_id: str) -> tuple[float, int]:
            latest_date = cluster_latest_dates.get(cl_id, epoch_min)
            # CLUSTER_ORDER内のインデックスを取得（無い場合は後ろに）
            order_idx = CLUSTER_ORDER.index(cl_id) if cl_id in CLUSTER_ORDER else len(CLUSTER_ORDER)
            # 最新日の降順(日付は負にしてソートさせるため、タイムスタンプベース)、順序の昇順
            return (-latest_date.timestamp(), order_idx)

        sorted_clusters = sorted(domain_clusters, key=cluster_sort_key)

        domain_html_parts = []
        for cl_id in sorted_clusters:
            # クラスタ内の記事を日付降順で取得
            cluster_arts = sorted(
                [a for a in articles if a["cluster_id"] == cl_id], key=lambda x: x["date"], reverse=True
            )
            if not cluster_arts:
                continue

            cl_info = CLUSTERS[cl_id]

            cluster_html = f"""            <div class="cluster-block">
                <h3>{cl_info["h3"]}</h3>
                <div class="article-row-list">"""

            for art in cluster_arts:
                date_str = art["date"].strftime("%Y-%m-%d")
                display_date = f"{art['date'].year}年{art['date'].month}月{art['date'].day}日"

                row_html = f"""                    <a class="article-row" href="articles/{art["filename"]}">
                        <div class="article-row-aside">
                            <time class="article-date" datetime="{date_str}">{display_date}</time>
                            <span class="article-row-eyebrow">{art["eyebrow"]}</span>
                        </div>
                        <div class="article-row-main">
                            <span class="article-row-title">{art["title"]}</span>
                            <p class="article-row-desc">{art["description"]}</p>
                        </div>
                        <span class="article-row-meta">{art["meta_text"]}</span>
                    </a>"""
                cluster_html += "\n" + row_html

            cluster_html += """
                </div>
            </div>"""
            domain_html_parts.append(cluster_html)

        domain_html_dict[domain] = (
            "\n".join(domain_html_parts)
            if domain_html_parts
            else '            <p class="empty-note">記事はまだありません。</p>'
        )

    # 4. index.html の更新
    index_path = os.path.join("public", "index.html")
    if not os.path.exists(index_path):
        logger.error(f"index.html not found at {index_path}. Generation aborted.")
        return

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index_content = f.read()

        # 新着セクションの置換
        recent_pattern = r"(<!-- BEGIN_RECENT_ARTICLES.*?-->).*?(<!-- END_RECENT_ARTICLES.*?-->)"
        index_content = re.sub(recent_pattern, f"\\1\n{recent_html}\n\\2", index_content, flags=re.DOTALL)

        # 各ドメインの置換
        for dom, dom_html in domain_html_dict.items():
            pattern_str = f"(<!-- BEGIN_{dom.upper()}_CLUSTERS.*?-->).*?(<!-- END_{dom.upper()}_CLUSTERS.*?-->)"
            index_content = re.sub(pattern_str, f"\\1\n{dom_html}\n\\2", index_content, flags=re.DOTALL)

        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_content)

        logger.info("Successfully updated public/index.html with current articles.")
    except Exception as e:
        logger.error(f"Failed to update index.html: {e}")


if __name__ == "__main__":
    main()
