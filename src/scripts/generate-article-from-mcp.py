import asyncio
import sys
import os
import re
import json
from datetime import datetime
import importlib.util

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp import ClientSession
from mcp.client.sse import sse_client
from app.chatmodel import ChatModel
from app.article_builder import ArticleBuilder
from app.utils.logger import logger

# 動的インポートでハイフン付きスクリプトを読み込む
script_dir = os.path.dirname(os.path.abspath(__file__))
sync_script_path = os.path.join(script_dir, "sync-article-dates.py")
spec = importlib.util.spec_from_file_location("sync_article_dates", sync_script_path)
sync_article_dates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_article_dates)

async def main():
    sse_url = "http://localhost:8000/sse"
    query = "MCP（Model Context Protocol）の概要と、主要なトランスポート（stdio, sse）の違いについて調査してください"
    research_text = ""

    logger.info("=== STEP 1: Deep Research MCP によるリサーチ実行 ===")
    logger.info(f"Connecting to deepresearchMCP via SSE at {sse_url}...")

    try:
        async with sse_client(sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logger.info("✅ ネットワーク経由（SSE）での疎通に成功しました。")

                logger.info(f"Calling tool 'run_deep_research' (timeout=1800s)...")
                # 20分以上かかる可能性があるため、wait_forで十分に長いタイムアウトを適用
                result = await asyncio.wait_for(
                    session.call_tool("run_deep_research", arguments={"query": query}),
                    timeout=1800.0
                )
                logger.info("✅ ツール実行結果を受信しました。")
                
                # 結果コンテンツの抽出
                if hasattr(result, "content"):
                    contents = result.content
                    text_parts = []
                    for content in contents:
                        if hasattr(content, "text"):
                            text_parts.append(content.text)
                        elif isinstance(content, dict) and "text" in content:
                            text_parts.append(content["text"])
                    research_text = "\n".join(text_parts)
                else:
                    research_text = str(result)
                    
    except Exception as e:
        logger.exception("❌ Deep Research実行中にエラーが発生しました:")
        return

    if not research_text.strip():
        logger.warning("⚠️ リサーチ結果テキストが空です。モックテキストまたは基本情報を使用して続行します。")
        research_text = (
            "MCP (Model Context Protocol) は、AIモデルとローカル/リモートの開発ツールやデータソースを"
            "接続するためのオープンスタンダード規格です。主要なトランスポート層として、"
            "ローカルで標準入出力を通して双方向通信を行う「stdio」と、ネットワーク経由で"
            "サーバーからクライアントにデータをイベント駆動で送信する「sse (Server-Sent Events)」がサポートされています。"
        )

    logger.info("=== STEP 2: ローカルLLMによる構造化JSONデータの生成 ===")
    model = ChatModel()
    
    prompt = f"""
以下のリサーチ結果をインプットとして、技術質問ノートに掲載するためのJSONデータを生成してください。

【リサーチインプット】
{research_text}

【制約・仕様】
- eyebrow（カテゴリ）: AI > 開発ワークフロー
- title（記事タイトル）: MCPの概要と主要なトランスポート（stdio, sse）の違い
- 以下のJSONスキーマに従って、余計な解説テキストは省き、純粋なJSON（```json ... ``` の中身）のみを返してください。

【JSONスキーマ】
{{
  "title": "記事タイトル",
  "eyebrow": "AI > 開発ワークフロー",
  "lead": "リード文（全体を要約した1段落、最大3文程度）",
  "qa": [
    {{
      "q": "質問内容",
      "a": "簡潔な回答"
    }}
  ],
  "sections": [
    {{
      "h2": "見出し",
      "paragraphs": [
        "本文段落1...",
        "本文段落2..."
      ],
      "subsections": [
        {{
          "h3": "小見出し",
          "paragraphs": [
            "サブ本文段落1..."
          ]
        }}
      ]
    }}
  ],
  "key_points": [
    "要点1",
    "要点2",
    "要点3"
  ],
  "references": [
    {{
      "title": "組織名/公式ドキュメント: ページタイトル",
      "url": "https://..."
    }}
  ]
}}
"""
    history = {
        "messages": [
            {"role": "system", "content": "あなたは技術記事の構造化JSONデータを生成する優秀なAIアシスタントです。指定されたJSON構造のみを出力してください。"},
            {"role": "user", "content": prompt}
        ]
    }
    
    logger.info("Requesting article data (JSON) from LocalLLM...")
    response = model.generate_response(history)
    if not response or not response.content:
        logger.error("Failed to generate article data from LocalLLM.")
        return
        
    raw_content = response.content
    logger.info(f"Received raw response from LLM (length: {len(raw_content)})")

    # LLMの出力をログファイルに残す
    try:
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "llm_output.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"=== LLM RESPONSE FROM MCP DATA AT {timestamp} ===\n")
            f.write(raw_content)
            f.write("\n\n")
        logger.info(f"Saved raw LLM response to {log_file}")
    except Exception as e:
        logger.warning(f"Failed to save raw LLM response to log file: {e}")

    json_content = raw_content.strip()
    json_block_match = re.search(r"```json\s*(.*?)\s*```", json_content, re.DOTALL)
    if json_block_match:
        json_content = json_block_match.group(1).strip()
    elif json_content.startswith("```"):
        json_content = re.sub(r"^```[a-zA-Z]*\n|```$", "", json_content).strip()

    try:
        data = json.loads(json_content)
    except Exception as e:
        logger.error(f"Failed to parse generated content as JSON: {e}")
        logger.debug(f"Raw response was: {json_content}")
        return

    logger.info("=== STEP 3: ArticleBuilder によるHTML記事のビルド ===")
    builder = ArticleBuilder()
    filename = "mcp-overview-transports.html"
    builder.save_article(data, filename)

    logger.info("=== STEP 4: sync-article-dates によるインデックス同期 ===")
    sync_article_dates.main()
    logger.info("🎉 E2E MCP-driven article generation completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
