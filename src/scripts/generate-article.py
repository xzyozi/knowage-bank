from datetime import datetime
import json
import os
import re
import sys

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import importlib.util

from app.article_builder import ArticleBuilder
from app.chatmodel import ChatModel
from app.utils.logger import logger

# 動的インポートでハイフン付きスクリプトを読み込む
script_dir = os.path.dirname(os.path.abspath(__file__))
sync_script_path = os.path.join(script_dir, "sync-article-dates.py")
spec = importlib.util.spec_from_file_location("sync_article_dates", sync_script_path)
assert spec is not None and spec.loader is not None
sync_article_dates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_article_dates)


def main() -> None:
    logger.info("Initializing LocalLLM for article generation...")

    # ChatModelインスタンスを作成（Ollamaのモデルを使用）
    model = ChatModel()

    # JSON構造データ生成用のプロンプト
    prompt = """
以下のテーマについて、技術質問ノートに掲載するためのJSONデータを生成してください。

【テーマ】
AIガバナンスと企業利用におけるリスク対策（情報漏洩、著作権、シャドーAI等のリスクと対策）

【制約・仕様】
- eyebrow（カテゴリ）: AI > 安全・運用
- title（記事タイトル）: AIガバナンスと企業利用におけるリスク対策
- 以下のJSONスキーマに従って、余計な解説テキストは省き、純粋なJSON（```json ... ``` の中身）のみを返してください。

【JSONスキーマ】
{
  "title": "記事タイトル",
  "eyebrow": "AI > 安全・運用",
  "lead": "リード文（全体を要約した1段落、最大3文程度）",
  "qa": [
    {
      "q": "質問内容",
      "a": "簡潔な回答"
    }
  ],
  "sections": [
    {
      "h2": "見出し",
      "paragraphs": [
        "本文段落1...",
        "本文段落2..."
      ],
      "subsections": [
        {
          "h3": "小見出し",
          "paragraphs": [
            "サブ本文段落1..."
          ]
        }
      ]
    }
  ],
  "key_points": [
    "要点1",
    "要点2",
    "要点3"
  ],
  "references": [
    {
      "title": "組織名/公式ドキュメント: ページタイトル",
      "url": "https://..."
    }
  ]
}
"""

    history = {
        "messages": [
            {
                "role": "system",
                "content": "あなたは技術記事の構造化JSONデータを生成する優秀なAIアシスタントです。余計なマークアップや説明を挟まず、指定されたJSON構造のみを出力してください。",
            },
            {"role": "user", "content": prompt},
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
            f.write(f"=== LLM RESPONSE AT {timestamp} ===\n")
            f.write(raw_content)
            f.write("\n\n")
        logger.info(f"Saved raw LLM response to {log_file}")
    except Exception as e:
        logger.warning(f"Failed to save raw LLM response to log file: {e}")

    json_content = raw_content.strip()

    # markdownのコードブロック（```json ... ```）で囲まれている場合は中身を抽出
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

    # ArticleBuilderのインスタンス化と実行
    builder = ArticleBuilder()
    filename = "ai-governance-corporate-risks.html"

    logger.info("Building HTML from JSON using ArticleBuilder...")
    builder.save_article(data, filename)

    # インデックスを同期
    logger.info("Running sync-article-dates script to update index.html...")
    sync_article_dates.main()
    logger.info("LocalLLM-driven end-to-end JSON generation verification completed!")


if __name__ == "__main__":
    main()
