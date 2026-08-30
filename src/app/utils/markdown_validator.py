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


def validate_markdown(markdown_text: str) -> ValidationResult:
    """Markdown 原本の構文・安全性・構成要素を検証する。"""
    result = ValidationResult()

    if not markdown_text or not markdown_text.strip():
        result.add_error("Markdown text is empty.")
        return result

    # 1. 未閉鎖コードフェンスのチェック
    fence_count = len(re.findall(r"^```", markdown_text, re.MULTILINE))
    if fence_count % 2 != 0:
        result.add_error(f"Unclosed code fence detected (count: {fence_count}).")

    # 2. 危険な生HTML・スクリプトのチェック
    if DANGEROUS_HTML_PATTERN.search(markdown_text):
        result.add_error("Forbidden or dangerous HTML tags/attributes detected in Markdown.")

    # 3. 未対応の見出し構文 (H4以降: ####) のチェック
    if re.search(r"^####+\s+", markdown_text, re.MULTILINE):
        result.add_error("Unsupported heading syntax H4 or deeper (####) detected.")

    # 4. URLの完全性・HTTPS限定チェック
    # Markdown リンク [title](url) の抽出
    link_matches = re.findall(r"\[([^\]]+)\]\(([^\)]+)\)", markdown_text)
    for title, url in link_matches:
        url_clean = url.strip()
        # 内部アンカー (#...) および相対パス (/... または ./...) は許可
        if url_clean.startswith("#") or url_clean.startswith("/") or url_clean.startswith("./"):
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
        # 内部アンカー (#...) は許可
        if href_clean.startswith("#"):
            continue
        if not validate_url(href_clean):
            result.add_error(f"Non-HTTPS or invalid URL found in href attribute: '{href_clean}'")

    return result
