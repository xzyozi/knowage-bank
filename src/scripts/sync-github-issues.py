import asyncio
import os
import sys
import argparse
import time
import re
import json
from datetime import datetime

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.issue_manager import IssueManager
from app.chatmodel import ChatModel
from app.article_builder import ArticleBuilder
from app.utils.logger import logger

# 動的インポートでハイフン付きスクリプトを読み込む
script_dir = os.path.dirname(os.path.abspath(__file__))
sync_script_path = os.path.join(script_dir, "sync-article-dates.py")
spec = importlib_util_spec = None
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("sync_article_dates", sync_script_path)
    sync_article_dates = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync_article_dates)
except Exception as e:
    logger.error(f"Failed to import sync-article-dates: {e}")

def sanitize_filename(title: str, number: int) -> str:
    """Issueタイトルから安全なファイル名を生成する。日本語の場合はissue-{number}.htmlにフォールバック"""
    # 英数字とハイフンだけを抽出
    cleaned = title.lower().strip()
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    
    # アルファベットが全く含まれない、または短すぎる場合は issue-番号.html にする
    if not re.search(r"[a-z]", cleaned) or len(cleaned) < 3:
        return f"issue-{number}.html"
    
    return f"issue-{number}-{cleaned[:30]}.html"

async def process_single_issue(issue: dict, manager: IssueManager) -> bool:
    issue_num = issue["number"]
    title = issue["title"]
    body = issue.get("body", "")
    
    logger.info(f"🚀 Starting generation for Issue #{issue_num}: {title}")
    manager.update_issue_status(issue_num, "processing")
    
    try:
        model = ChatModel()
        
        # 記事生成プロンプト（Issueのタイトルと本文をインプットとする）
        prompt = f"""
以下のGitHub Issueの内容に基づいて、技術質問ノートに掲載するための構造化JSONデータを生成してください。

【Issueのタイトル】
{title}

【Issueの本文】
{body}

【制約・仕様】
- eyebrow（カテゴリ）: AI > 開発ワークフロー  (※内容に応じて既存の適切なカテゴリに変更してください)
- title（記事タイトル）: {title}
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
        
        logger.info("Requesting article generation from LocalLLM...")
        response = model.generate_response(history)
        if not response or not response.content:
            raise Exception("Empty response from LocalLLM")
            
        raw_content = response.content
        json_content = raw_content.strip()
        
        # markdownコードブロックの抽出
        json_block_match = re.search(r"```json\s*(.*?)\s*```", json_content, re.DOTALL)
        if json_block_match:
            json_content = json_block_match.group(1).strip()
        elif json_content.startswith("```"):
            json_content = re.sub(r"^```[a-zA-Z]*\n|```$", "", json_content).strip()
            
        data = json.loads(json_content)
        
        # HTML記事の構築と保存
        builder = ArticleBuilder()
        filename = sanitize_filename(title, issue_num)
        
        logger.info(f"Building HTML and saving to {filename}...")
        builder.save_article(data, filename)
        
        # インデックスの同期
        logger.info("Running sync-article-dates to update index.html...")
        sync_article_dates.main()
        
        # ステータスを完了に更新
        manager.update_issue_status(issue_num, "processed", article_file=filename)
        logger.info(f"✅ Successfully processed Issue #{issue_num}!")
        return True

    except Exception as e:
        logger.exception(f"❌ Failed to process Issue #{issue_num}:")
        manager.update_issue_status(issue_num, "failed")
        return False

async def main():
    parser = argparse.ArgumentParser(description="Sync GitHub Issues and generate articles.")
    parser.add_argument("--run-once", action="store_true", help="Run sync and process one issue, then exit.")
    parser.add_argument("--interval", type=int, default=1800, help="Polling interval in seconds (default: 1800s / 30m).")
    args = parser.parse_args()

    manager = IssueManager()

    logger.info("Starting GitHub Issue Sync daemon...")
    
    while True:
        logger.info("=== Starting Sync Cycle ===")
        # 1. GitHub APIと同期
        manager.sync_issues()
        
        # 2. 未処理のIssueを1件取得
        next_issue = manager.get_next_unprocessed_issue()
        
        if next_issue:
            logger.info(f"Found unprocessed Issue #{next_issue['number']}. Processing...")
            await process_single_issue(next_issue, manager)
        else:
            logger.info("No unprocessed issues found in this cycle.")
            
        if args.run_once:
            logger.info("Run-once flag detected. Exiting.")
            break
            
        logger.info(f"Sleeping for {args.interval} seconds until next cycle...")
        await asyncio.sleep(args.interval)

if __name__ == "__main__":
    asyncio.run(main())
