"""Markdown原本の保存・管理およびHTML再生成モジュール。

LLMが出力したMarkdownを data/article_sources/issue-<番号>.md に原子的書込みで物理保存し、
外部リサーチやLLM呼び出しなしでHTMLを再ビルドできるようにする。
"""

import os
from typing import Optional

from app.article_builder import ArticleBuilder
from app.utils.atomic_file import atomic_write_text
from app.utils.logger import logger


def get_default_source_dir() -> str:
    """Markdown原本のデフォルト格納ディレクトリパスを取得する。"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "article_sources"))


def save_article_source(
    issue_number: int,
    markdown_text: str,
    source_dir: Optional[str] = None,
) -> str:
    """Markdown原本を data/article_sources/issue-<番号>.md に保存する。"""
    target_dir = source_dir or get_default_source_dir()
    os.makedirs(target_dir, exist_ok=True)

    filename = f"issue-{issue_number}.md"
    output_path = os.path.join(target_dir, filename)

    atomic_write_text(output_path, markdown_text)

    with open(output_path, "r", encoding="utf-8") as f:
        read_back = f.read()
    if read_back != markdown_text:
        raise ValueError(f"Saved article source content mismatch for issue #{issue_number}: {output_path}")

    logger.info(f"Article source saved and verified successfully: {output_path}")
    return output_path


def load_article_source(
    issue_number: int,
    source_dir: Optional[str] = None,
) -> str:
    """保存済みの Markdown 原本テキストを読み込む。"""
    target_dir = source_dir or get_default_source_dir()
    filename = f"issue-{issue_number}.md"
    file_path = os.path.join(target_dir, filename)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Article source file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def rebuild_article_from_source(
    issue_number: int,
    output_filename: str,
    source_dir: Optional[str] = None,
    builder: Optional[ArticleBuilder] = None,
) -> str:
    """保存済みの Markdown 原本から HTML 記事を完全オフラインで再生成する。"""
    markdown_text = load_article_source(issue_number, source_dir=source_dir)
    article_builder = builder or ArticleBuilder()

    data = {"markdown_text": markdown_text}
    output_path = article_builder.save_article(data, output_filename)
    logger.info(f"Successfully rebuilt HTML article for Issue #{issue_number} from source: {output_path}")
    return output_path
