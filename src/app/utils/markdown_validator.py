"""Markdown, HTML, および URL の許可方式検証（バリデーション）モジュール。

副作用を持たず、検証結果 DTO (ValidationResult) を返却する。
"""

from dataclasses import dataclass, field
import re
from urllib.parse import urlparse


@dataclass
class ValidationResult:
    """検証結果 DTO。"""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.is_valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


# 危険な生HTMLタグ・属性の正規表現
DANGEROUS_HTML_PATTERN = re.compile(
    r"<\s*(script|iframe|style|object|embed|link|meta|form|input|button|applet|base)\b"
    r"|on\w+\s*=",
    re.IGNORECASE,
)
RAW_HTML_TAG_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")
REFERENCE_ENTRY_PATTERN = re.compile(
    r"^\[(?P<numbers>\d+(?:\s*,\s*\d+)*)\]\s+(?P<title>.+?)"
    r"(?:\s*\(source nr:.*?\))?\s*$\n\s*URL:\s*(?P<url>\S+)\s*$",
    re.MULTILINE,
)
CITATION_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")

# HTML出力のテンプレートで利用する内部アンカー・相対パス。
ALLOWED_RELATIVE_PREFIXES = ("#", "/", "./", "../")
REQUIRED_FRONTMATTER_FIELDS = ("title", "eyebrow", "lead")
ALLOWED_MARKDOWN_RELATIVE_LINK_PATTERN = re.compile(
    r"(?:/articles/|\./|\.\./articles/)[A-Za-z0-9][A-Za-z0-9._-]*\.html(?:#[A-Za-z0-9][A-Za-z0-9._-]*)?$"
)


def validate_url(url: str) -> bool:
    """URL が安全な HTTPS 絶対 URL かどうかを検証する。"""
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() != "https":
            return False
        if not parsed.netloc:
            return False
        # 資格情報(user:pass@host)や制御文字の排除
        if "@" in parsed.netloc or re.search(r"[\x00-\x1f\x7f]", url):
            return False
        return True
    except Exception:
        return False


def _extract_frontmatter(markdown_text: str, result: ValidationResult) -> str:
    """先頭の簡易YAML frontmatterを検証し、本文を返す。"""
    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        result.add_error("Markdown must start with a YAML frontmatter delimiter (---).")
        return markdown_text

    closing_index = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing_index is None:
        result.add_error("YAML frontmatter closing delimiter (---) is missing.")
        return ""

    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            result.add_error(f"Invalid frontmatter entry: '{stripped}'.")
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or not value:
            result.add_error(f"Frontmatter field '{key or stripped}' must have a non-empty value.")
            continue
        if key in metadata:
            result.add_error(f"Duplicate frontmatter field: '{key}'.")
            continue
        metadata[key] = value

    for field_name in REQUIRED_FRONTMATTER_FIELDS:
        if not metadata.get(field_name):
            result.add_error(f"Missing required frontmatter field: '{field_name}'.")

    return "\n".join(lines[closing_index + 1 :])


def _remove_code_fences(markdown_text: str) -> str:
    """コードフェンス内を構文検証対象から除外する。"""
    return re.sub(r"^```.*?^```\s*$", "", markdown_text, flags=re.MULTILINE | re.DOTALL)


def _is_allowed_markdown_relative_link(url: str) -> bool:
    """記事Markdownで許容する内部リンクだけを判定する。"""
    if url.startswith("#"):
        return len(url) > 1 and not re.search(r"[\x00-\x1f\x7f\s]", url)
    return bool(ALLOWED_MARKDOWN_RELATIVE_LINK_PATTERN.fullmatch(url))


def _validate_unsupported_markdown_syntax(markdown_text: str, result: ValidationResult) -> None:
    """HTML変換器が意味を保てないMarkdown構文を明示的に拒否する。"""
    if RAW_HTML_TAG_PATTERN.search(markdown_text):
        result.add_error("Raw HTML is not supported in Markdown.")
    if re.search(r"^#(?!#)\s+", markdown_text, re.MULTILINE):
        result.add_error("Unsupported H1 heading in body; use frontmatter title and H2/H3 headings.")
    if re.search(r"^####+\s+", markdown_text, re.MULTILINE):
        result.add_error("Unsupported heading syntax H4 or deeper (####) detected.")
    if re.search(r"^\s*>\s?", markdown_text, re.MULTILINE):
        result.add_error("Block quotes are not supported in Markdown.")
    if re.search(r"!\[[^\]]*\]\([^\)]+\)", markdown_text):
        result.add_error("Images are not supported in Markdown.")
    if re.search(r"\[\^[^\]]+\]", markdown_text):
        result.add_error("Footnotes are not supported in Markdown.")
    if re.search(r"^\s*[-*+]\s+\[[ xX]\]\s+", markdown_text, re.MULTILINE):
        result.add_error("Task lists are not supported in Markdown.")
    if re.search(r"^[ \t]+(?:[-*+]\s+|\d+\.\s+)", markdown_text, re.MULTILINE):
        result.add_error("Nested lists are not supported in Markdown.")


def _validate_citations_and_references(markdown_text: str, result: ValidationResult) -> None:
    """本文の引用番号と末尾参考文献フッターの一対一対応を検証する。"""
    reference_matches = list(REFERENCE_ENTRY_PATTERN.finditer(markdown_text))
    if "URL:" in markdown_text and not reference_matches:
        result.add_error("Malformed reference entry; use '[N] title' followed by 'URL: https://...'.")
        return

    reference_numbers: set[int] = set()
    for match in reference_matches:
        for number_text in match.group("numbers").split(","):
            number = int(number_text.strip())
            if number in reference_numbers:
                result.add_error(f"Duplicate reference number: [{number}].")
            reference_numbers.add(number)
        if not validate_url(match.group("url")):
            result.add_error(f"Invalid or non-HTTPS URL in reference: '{match.group('url')}'")

    if reference_matches:
        footer_start = reference_matches[0].start()
        footer_text = markdown_text[footer_start:]
        footer_remainder = REFERENCE_ENTRY_PATTERN.sub("", footer_text)
        footer_remainder = re.sub(
            r"^\s*#{1,3}\s*(?:出典|参考文献|参考資料)\s*$",
            "",
            footer_remainder,
            flags=re.MULTILINE,
        )
        if footer_remainder.strip():
            result.add_error("Reference entries must be contiguous at the end of Markdown.")

    body_text = REFERENCE_ENTRY_PATTERN.sub("", markdown_text)
    citation_numbers = {
        int(number_text.strip())
        for match in CITATION_PATTERN.finditer(body_text)
        for number_text in match.group(1).split(",")
    }
    if citation_numbers and not reference_numbers:
        result.add_error("Citations require matching reference entries.")
    for number in sorted(citation_numbers - reference_numbers):
        result.add_error(f"Citation [{number}] has no matching reference entry.")
    for number in sorted(reference_numbers - citation_numbers):
        result.add_error(f"Reference [{number}] is not cited in the article body.")


def validate_markdown(markdown_text: str) -> ValidationResult:
    """Markdown 原本の構文・安全性・構成要素を検証する。"""
    result = ValidationResult()

    if not markdown_text or not markdown_text.strip():
        result.add_error("Markdown text is empty.")
        return result

    body_text = _extract_frontmatter(markdown_text, result)

    # 未閉鎖コードフェンスを先に判定し、閉鎖済みフェンス内は構文検証から除外する。
    fence_count = len(re.findall(r"^```", body_text, re.MULTILINE))
    if fence_count % 2 != 0:
        result.add_error(f"Unclosed code fence detected (count: {fence_count}).")
    inspectable_text = _remove_code_fences(body_text)

    if DANGEROUS_HTML_PATTERN.search(inspectable_text):
        result.add_error("Forbidden or dangerous HTML tags/attributes detected in Markdown.")
    _validate_unsupported_markdown_syntax(inspectable_text, result)
    _validate_citations_and_references(inspectable_text, result)

    for title, url in MARKDOWN_LINK_PATTERN.findall(inspectable_text):
        url_clean = url.strip()
        if _is_allowed_markdown_relative_link(url_clean):
            continue
        if not validate_url(url_clean):
            result.add_error(f"Invalid or non-HTTPS URL in link '{title}': '{url_clean}'")

    return result


def validate_html(html_text: str) -> ValidationResult:
    """生成された HTML の構造および安全性を検証する。"""
    result = ValidationResult()

    if not html_text or not html_text.strip():
        result.add_error("HTML text is empty.")
        return result

    # 1. 必須構造のチェック
    if "<!doctype html>" not in html_text.lower():
        result.add_error("Missing DOCTYPE declaration.")

    if 'lang="ja"' not in html_text and "lang='ja'" not in html_text:
        result.add_error("Missing lang='ja' attribute in <html> tag.")

    if "<title>" not in html_text:
        result.add_error("Missing <title> tag.")

    if "<article" not in html_text and "<main" not in html_text:
        result.add_error("Missing <article> or <main> container element.")

    # 2. href 属性の非 HTTPS チェック (http:// や javascript: を検出)
    href_matches = re.findall(r'href=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    for href in href_matches:
        href_clean = href.strip()
        # 内部アンカー (#...) および相対パス (/, ./, ../) は許可
        if href_clean.startswith(ALLOWED_RELATIVE_PREFIXES):
            continue
        if not validate_url(href_clean):
            result.add_error(f"Non-HTTPS or invalid URL found in href attribute: '{href_clean}'")

    return result
