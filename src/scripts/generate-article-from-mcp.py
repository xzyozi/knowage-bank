"""Deep Research MCPの結果からMarkdown記事を生成し、HTMLとindexを同期するCLI。"""

import asyncio
import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import TextContent

from app.article_builder import ArticleBuilder
from app.chatmodel import ChatModel
from app.utils.logger import logger
from app.utils.markdown_validator import validate_markdown

script_dir = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sync_article_dates", os.path.join(script_dir, "sync-article-dates.py"))
assert spec is not None and spec.loader is not None
sync_article_dates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_article_dates)

SSE_URL = "http://localhost:8000/sse"
ARTICLE_TITLE = "MCPの概要と主要なトランスポート（stdio、SSE）の違い"
ARTICLE_EYEBROW = "AI > 開発ワークフロー"
OUTPUT_FILENAME = "aws-kiro-transition-from-cursor.html"
RESEARCH_QUERY = "MCPの概要、stdioとSSEの違い、CursorからKiroへ移行する際の手順を調査してください。"


def _strip_markdown_fence(content: str) -> str:
    text = content.strip()
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1] == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


async def _get_research_text() -> str:
    async with sse_client(SSE_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await asyncio.wait_for(
                session.call_tool("run_deep_research", arguments={"query": RESEARCH_QUERY}), timeout=1800.0
            )
    if not hasattr(result, "content"):
        return str(result)
    return "\n".join(content.text for content in result.content if isinstance(content, TextContent))


async def main() -> None:
    try:
        research_text = await _get_research_text()
    except Exception:
        logger.exception("Deep Research MCP execution failed.")
        return
    if not research_text.strip():
        logger.error("Deep Research MCP returned no text.")
        return

    prompt = f"""以下のリサーチ結果を基に、技術質問ノート向けのMarkdown記事のみを生成してください。

タイトル: {ARTICLE_TITLE}
カテゴリ: {ARTICLE_EYEBROW}
リサーチ結果:\n{research_text}

先頭にtitle、eyebrow、leadを含むYAML Frontmatterを置き、H2/H3、要点、FAQ、参考文献を含めてください。JSON、HTML、説明文、外側のコードフェンスは出力しないでください。"""
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

    markdown_text = _strip_markdown_fence(raw_content)
    validation = validate_markdown(markdown_text)
    if not validation.is_valid:
        logger.error(f"Generated Markdown validation failed: {'; '.join(validation.errors)}")
        return

    ArticleBuilder().save_article({"markdown_text": markdown_text}, OUTPUT_FILENAME)
    if not sync_article_dates.main():
        logger.error("Failed to synchronize index.html after Markdown article generation.")
        return
    logger.info("MCP-driven end-to-end Markdown generation completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
