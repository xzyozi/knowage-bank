"""ローカルLLMからMarkdown記事を生成し、HTMLとindexを同期するCLI。"""

from datetime import datetime
import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.article_builder import ArticleBuilder
from app.chatmodel import ChatModel
from app.utils.logger import logger
from app.utils.markdown_validator import validate_markdown

script_dir = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sync_article_dates", os.path.join(script_dir, "sync-article-dates.py"))
assert spec is not None and spec.loader is not None
sync_article_dates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_article_dates)

ARTICLE_TITLE = "AIガバナンスと企業利用におけるリスク対策"
ARTICLE_EYEBROW = "AI > 安全・運用"
OUTPUT_FILENAME = "ai-governance-corporate-risks.html"


def _strip_markdown_fence(content: str) -> str:
    """LLMがMarkdown全体をコードフェンスで囲んだ場合だけ除去する。"""
    text = content.strip()
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1] == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _log_raw_response(content: str) -> None:
    os.makedirs("logs", exist_ok=True)
    with open(os.path.join("logs", "llm_output.log"), "a", encoding="utf-8", newline="\n") as f:
        f.write(f"=== LLM MARKDOWN RESPONSE AT {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{content}\n\n")


def main() -> None:
    logger.info("Initializing LocalLLM for Markdown article generation...")
    prompt = f"""以下のテーマについて、技術質問ノート向けのMarkdown記事のみを生成してください。

テーマ: {ARTICLE_TITLE}
カテゴリ: {ARTICLE_EYEBROW}

先頭にtitle、eyebrow、leadを含むYAML Frontmatterを置いてください。本文はH2/H3、要点、FAQ、参考文献を含めてください。JSON、HTML、説明文、外側のコードフェンスは出力しないでください。"""
    response = ChatModel().generate_response(
        {
            "messages": [
                {"role": "system", "content": "あなたはMarkdown技術記事を生成するアシスタントです。"},
                {"role": "user", "content": prompt},
            ]
        }
    )
    raw_content = response.content if response and response.content else None
    if not raw_content:
        logger.error("Failed to generate Markdown article from LocalLLM.")
        return

    _log_raw_response(raw_content)
    markdown_text = _strip_markdown_fence(raw_content)
    validation = validate_markdown(markdown_text)
    if not validation.is_valid:
        logger.error(f"Generated Markdown validation failed: {'; '.join(validation.errors)}")
        return

    ArticleBuilder().save_article({"markdown_text": markdown_text}, OUTPUT_FILENAME)
    if not sync_article_dates.main():
        logger.error("Failed to synchronize index.html after Markdown article generation.")
        return
    logger.info("LocalLLM-driven end-to-end Markdown generation completed successfully.")


if __name__ == "__main__":
    main()
