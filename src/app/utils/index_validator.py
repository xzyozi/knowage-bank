"""public/index.html の生成結果の整合性検証モジュール。

保存済みの index.html を再読込みした結果に対し、リンク先記事の実在性、
タイトル・日付の整合性、同一セクション内の重複を検証する。
副作用を持たず、検証結果 DTO (ValidationResult) を返却する。
"""

import os
import re
from typing import Any

from app.utils.markdown_validator import ValidationResult

__all__ = ["ValidationResult", "IndexSyncError", "validate_index_html"]


class IndexSyncError(Exception):
    """index.html の原子的保存・保存後検証・失敗時復元のいずれかが失敗したことを表す例外。"""


_LINK_BLOCK_PATTERN = re.compile(
    r'<a\s+class="article-(?:card|row)"\s+href="articles/([^"]+)">(.*?)</a>',
    re.DOTALL,
)
_TITLE_PATTERNS = (
    re.compile(r"<h4>(.*?)</h4>", re.DOTALL),
    re.compile(r'<span class="article-row-title">(.*?)</span>', re.DOTALL),
)
_DATE_PATTERN = re.compile(r'<time[^>]*\bdatetime="([^"]+)"')
_HREF_PATTERN = re.compile(r'href="articles/([^"]+)"')
_RECENT_SECTION_PATTERN = re.compile(
    r"<!-- BEGIN_RECENT_ARTICLES.*?-->(.*?)<!-- END_RECENT_ARTICLES.*?-->", re.DOTALL
)
_DOMAINS = ("dev", "game", "ai", "infra")


def _extract_title(block: str) -> str | None:
    for pattern in _TITLE_PATTERNS:
        m = pattern.search(block)
        if m:
            return m.group(1).strip()
    return None


def _check_section_duplicates(section_content: str, section_name: str, result: ValidationResult) -> None:
    hrefs = _HREF_PATTERN.findall(section_content)
    seen: set[str] = set()
    duplicated: set[str] = set()
    for href in hrefs:
        if href in seen:
            duplicated.add(href)
        seen.add(href)
    for href in sorted(duplicated):
        result.add_error(f"Duplicate article link 'articles/{href}' detected in {section_name}.")


def validate_index_html(
    index_html: str,
    articles: list[dict[str, Any]],
    articles_dir: str,
) -> ValidationResult:
    """保存済み index.html の内容を検証する。

    Args:
        index_html: 保存直後に再読込みした index.html の内容。
        articles: index.html 生成時に使用した記事メタデータのリスト
            （`filename`, `title`, `date` を含む辞書）。
        articles_dir: 記事HTMLが実際に存在するディレクトリパス。

    Returns:
        ValidationResult: 検証結果。`is_valid=False` の場合は `errors` に理由を格納する。
    """
    result = ValidationResult()

    if not index_html or not index_html.strip():
        result.add_error("index.html content is empty.")
        return result

    article_lookup = {a["filename"]: a for a in articles}

    for filename, block in _LINK_BLOCK_PATTERN.findall(index_html):
        article_path = os.path.join(articles_dir, filename)
        if not os.path.exists(article_path):
            result.add_error(f"Linked article file does not exist: articles/{filename}")
            continue

        expected = article_lookup.get(filename)
        if expected is None:
            result.add_warning(f"Linked article 'articles/{filename}' is not part of the generated article metadata.")
            continue

        title_text = _extract_title(block)
        if title_text is None:
            result.add_error(f"Could not extract title for linked article: articles/{filename}")
        elif title_text != expected["title"]:
            result.add_error(
                f"Title mismatch for articles/{filename}: index has '{title_text}', expected '{expected['title']}'."
            )

        date_match = _DATE_PATTERN.search(block)
        expected_date_str = expected["date"].strftime("%Y-%m-%d")
        if date_match is None:
            result.add_error(f"Could not extract date for linked article: articles/{filename}")
        elif date_match.group(1) != expected_date_str:
            result.add_error(
                f"Date mismatch for articles/{filename}: index has '{date_match.group(1)}', "
                f"expected '{expected_date_str}'."
            )

    recent_match = _RECENT_SECTION_PATTERN.search(index_html)
    if recent_match:
        _check_section_duplicates(recent_match.group(1), "recent articles section", result)

    for domain in _DOMAINS:
        domain_pattern = re.compile(
            rf"<!-- BEGIN_{domain.upper()}_CLUSTERS.*?-->(.*?)<!-- END_{domain.upper()}_CLUSTERS.*?-->", re.DOTALL
        )
        domain_match = domain_pattern.search(index_html)
        if domain_match:
            _check_section_duplicates(domain_match.group(1), f"'{domain}' domain section", result)

    return result
