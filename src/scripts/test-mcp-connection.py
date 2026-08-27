import asyncio
import os
import sys

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp import ClientSession
from mcp.client.sse import sse_client

from app.utils.logger import logger


async def main() -> None:
    # 常時起動しているサーバーのエンドポイントを指定
    sse_url = "http://localhost:8000/sse"

    logger.info(f"Connecting to deepresearchMCP via SSE at {sse_url}...")

    try:
        # HTTP経由で接続テスト（疎通確認）
        async with sse_client(sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 🟢 疎通確認
                await session.initialize()
                logger.info("✅ ネットワーク経由（SSE）での疎通に成功しました。")

                # 🟢 ツール取得
                tools_result = await session.list_tools()
                # SDKのバージョンによって返り値が ListToolsResult か iterable か異なるため安全にパース
                tools = getattr(tools_result, "tools", tools_result)
                logger.info(f"検出ツール: {[getattr(t, 'name', str(t)) for t in tools]}")

                # 🟢 ツール実行
                logger.info("Calling tool 'run_deep_research' with specific query (timeout=1800s)...")
                query = "MCP（Model Context Protocol）の概要と、主要なトランスポート（stdio, sse）の違いについて調査してください"
                result = await asyncio.wait_for(
                    session.call_tool("run_deep_research", arguments={"query": query}), timeout=1800.0
                )
                logger.info(f"ツール実行結果: {result}")
    except Exception:
        logger.exception("❌ 接続または実行中にエラーが発生しました:")


if __name__ == "__main__":
    asyncio.run(main())
