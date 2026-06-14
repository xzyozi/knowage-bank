import asyncio
import sys
import os

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp import ClientSession
from mcp.client.sse import sse_client
from app.utils.logger import logger

async def main():
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
                if hasattr(tools_result, "tools"):
                    tools = tools_result.tools
                else:
                    tools = tools_result
                logger.info(f"検出ツール: {[t.name for t in tools]}")
                
                # 🟢 ツール実行
                logger.info("Calling tool 'run_deep_research' with query 'テスト'...")
                result = await session.call_tool("run_deep_research", arguments={"query": "テスト"})
                logger.info(f"ツール実行結果: {result}")
    except Exception as e:
        logger.exception("❌ 接続または実行中にエラーが発生しました:")

if __name__ == "__main__":
    asyncio.run(main())
