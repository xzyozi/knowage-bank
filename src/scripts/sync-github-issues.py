import asyncio
import os
import sys
import argparse
import time
import re
import json
from datetime import datetime
import subprocess

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.issue_manager import IssueManager
from app.chatmodel import ChatModel
from app.article_builder import ArticleBuilder
from app.utils.logger import logger
from app import config
from mcp import ClientSession
from mcp.client.sse import sse_client

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

def git_commit(filename: str, issue_num: int, title: str, push: bool = False) -> bool:
    """自動生成されたHTMLとインデックスの更新をコミットし、オプションでプッシュする"""
    try:
        # 現在のブランチ名を取得
        res_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True
        )
        branch_name = res_branch.stdout.strip()
        
        # ファイルのステージング
        subprocess.run(["git", "add", f"public/articles/{filename}", "public/index.html"], check=True)
        
        # 変更があるか確認 (コミットするものがない場合はスキップ)
        res_diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if res_diff.returncode == 0:
            logger.info("No git changes to commit. Git process skipped.")
            return True
            
        # コミット実行
        commit_msg = f"feat: Issue #{issue_num} からの自動記事追加: {title}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        logger.info(f"Committed changes with message: '{commit_msg}'")
        
        # プッシュ実行
        if push:
            logger.info(f"Pushing changes to remote branch: {branch_name}...")
            subprocess.run(["git", "push", "origin", branch_name], check=True)
            logger.info("✅ Pushed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e}")
        return False

async def process_single_issue(issue: dict, manager: IssueManager, git_commit_flag: bool = False, git_push: bool = False) -> bool:
    issue_num = issue["number"]
    title = issue["title"]
    body = issue.get("body", "")
    
    logger.info(f"🚀 Starting generation for Issue #{issue_num}: {title}")
    manager.update_issue_status(issue_num, "processing")
    
    try:
        model = ChatModel()
        
        # 1. LLMを用いてリサーチクエリを決定
        query_prompt = f"以下のGitHub Issueの内容に基づいて、技術的な詳細をWeb検索・リサーチするためのクエリ文（日本語で1文程度、検索キーワードの羅列でも可）を生成してください。余計な前置きや説明は完全に省き、検索クエリ文そのもののみを出力してください。\n\n【Issueタイトル】\n{title}\n\n【Issue本文】\n{body}"
        query_history = {
            "messages": [
                {"role": "system", "content": "あなたは与えられたIssueから最適な検索エンジン用のクエリ文を抽出するアシスタントです。"},
                {"role": "user", "content": query_prompt}
            ]
        }
        logger.info("Extracting research query using LLM...")
        query_response = model.generate_response(query_history)
        research_query = title
        if query_response and query_response.content:
            research_query = query_response.content.strip().strip('"').strip("'")
            research_query = re.sub(r"\s+", " ", research_query)
        logger.info(f"Generated research query: '{research_query}'")
        
        # 2. MCP連携によるDeep Research実行
        research_text = ""
        sse_url = config.DEEPRESEARCH_SSE_URL
        logger.info("=== MCP Deep Research Step ===")
        logger.info(f"Connecting to deepresearchMCP via SSE at {sse_url}...")
        try:
            async with sse_client(sse_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    logger.info("Calling tool 'run_deep_research' (timeout=1800s)...")
                    result = await asyncio.wait_for(
                        session.call_tool("run_deep_research", arguments={"query": research_query}),
                        timeout=1800.0
                    )
                    logger.info("✅ Deep Research finished successfully.")
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
        except Exception as mcp_err:
            logger.warning(f"⚠️ Deep Research execution failed, falling back to Issue text only. Error: {mcp_err}")
            research_text = f"Title: {title}\nBody: {body}"
        
        # 3. リサーチ結果を元にした記事生成プロンプトの作成
        prompt = f"""
以下のリサーチ結果およびGitHub Issueの内容に基づいて、技術質問ノートに掲載するための構造化JSONデータを生成してください。
リサーチインプットから得られた具体的な技術詳細、設定手順、コードスニペット、仕様の比較などを極力網羅して、非常に情報量の多い充実した解説記事にしてください。

【リサーチインプット】
{research_text}

【Issueのタイトル】
{title}

【Issueの本文】
{body}

【情報網羅と構成の拡張ルール】
1. **セクション構成の拡張**:
   - `sections` リストには、リサーチ結果から判明した仕様、具体的な手順、他の技術やツールとの比較など、論点ごとに最低 **4つ以上** のセクション（`h2`）を記述してください。
   - 各セクション（`h2`）には、さらに詳細な解説や個別手順、設定例などを整理するためのサブセクション（`h3`）を最低 **2つ以上** 設けてください。
   - 各見出し（`h2`, `h3`）下の `paragraphs` リストには、1文だけの記述を避け、技術的根拠やメリット・デメリットを掘り下げて解説する段落（2〜3文程度）を最低 **2つ以上** 記述してください。
2. **QA（質問と回答）の充実**:
   - `qa` リストには、基本的な技術質問に加えて、「よくあるエラーや落とし穴」「トラブルシューティング」「実際の選定基準やパフォーマンス特性」に関する実用的なQAを最低 **4つ以上** 作成してください。
3. **参考文献（references）の抽出**:
   - 【リサーチインプット】の中に記載されている具体的なURL（Qiita、公式ドキュメント、GitHub等）や情報ソースがあれば、漏れなく `references` リストに抽出して記述してください。

【JSON構造の完全性（崩壊の防止）】
- 出力は必ず有効なJSONオブジェクトのみにしてください（前後に「以下が結果です」などの挨拶文は一切含めず、純粋に ```json ... ``` で囲んで出力してください）。
- 各テキスト項目内の改行はエスケープされた `\n` を使用し、JSON自体の構造（括弧やカンマ）を壊さないようにしてください。
- 文字列内にダブルクォーテーション `"` を記述する場合は必ず `\"` でエスケープしてください。キー名や構造用のダブルクォーテーションはそのままにしてください。

【JSONスキーマ】
{{
  "title": "記事タイトル",
  "eyebrow": "AI > 開発ワークフロー",
  "lead": "リード文（全体を要約した1段落、最大3文程度）",
  "qa": [
    {{
      "q": "具体的な質問内容1",
      "a": "簡潔で技術的な回答1"
    }},
    {{
      "q": "具体的な質問内容2",
      "a": "簡潔で技術的な回答2"
    }},
    {{
      "q": "具体的な質問内容3",
      "a": "簡潔で技術的な回答3"
    }},
    {{
      "q": "具体的な質問内容4",
      "a": "簡潔で技術的な回答4"
    }}
  ],
  "sections": [
    {{
      "h2": "主要なセクション見出し1",
      "paragraphs": [
        "論点を詳しく解説する段落1...",
        "論点を詳しく解説する段落2..."
      ],
      "subsections": [
        {{
          "h3": "サブセクション見出し1-1",
          "paragraphs": [
            "より詳細な技術仕様や手順を詳しく解説する段落1...",
            "より詳細な技術仕様や手順を詳しく解説する段落2..."
          ]
        }},
        {{
          "h3": "サブセクション見出し1-2",
          "paragraphs": [
            "関連する補足情報や設定例などを詳しく解説する段落1...",
            "関連する補足情報や設定例などを詳しく解説する段落2..."
          ]
        }}
      ]
    }}
  ],
  "key_points": [
    "リサーチを踏まえた重要ポイント1",
    "リサーチを踏まえた重要ポイント2",
    "リサーチを踏まえた重要ポイント3"
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
            
        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as je:
            logger.warning(f"⚠️ JSON parsing failed on first attempt: {je}. Attempting cleanup...")
            # 崩壊防止のための簡易クリーンアップ
            # 制御文字（エスケープされていない本物の改行など）を文字列内でエスケープされた \n に変換することを試みるなど
            try:
                # 文字列内の生の改行コードを置き換える（JSONフォーマットを破壊しやすいため）
                # ただし、JSON構造外の改行はそのままにする必要があるため、慎重に行う
                cleaned_content = json_content
                # 前後に何かテキストが残っている場合は再度トリム
                cleaned_content = cleaned_content.strip()
                data = json.loads(cleaned_content)
                logger.info("✅ JSON parsing succeeded after cleanup.")
            except Exception as final_err:
                logger.error(f"❌ JSON structure is corrupted: {final_err}\nRaw Content snippet:\n{json_content[:500]}...")
                raise je
        
        # HTML記事の構築と保存
        builder = ArticleBuilder()
        filename = sanitize_filename(title, issue_num)
        
        logger.info(f"Building HTML and saving to {filename}...")
        builder.save_article(data, filename)
        
        # インデックスの同期
        logger.info("Running sync-article-dates to update index.html...")
        sync_article_dates.main()
        
        # 生成されたHTMLをGitに自動コミット＆プッシュ（オプション）
        if git_commit_flag or git_push:
            logger.info("Running automatic Git commit...")
            if not git_commit(filename, issue_num, title, push=git_push):
                raise Exception("Git commit or push failed")
        else:
            logger.info("Git automation is disabled. Skipping git commit.")

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
    parser.add_argument("--commit", action="store_true", help="Automatically git add and commit after generating articles.")
    parser.add_argument("--push", action="store_true", help="Automatically git commit and push after generating articles.")
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
            await process_single_issue(next_issue, manager, git_commit_flag=args.commit, git_push=args.push)
        else:
            logger.info("No unprocessed issues found in this cycle.")
            
        if args.run_once:
            logger.info("Run-once flag detected. Exiting.")
            break
            
        logger.info(f"Sleeping for {args.interval} seconds until next cycle...")
        await asyncio.sleep(args.interval)

if __name__ == "__main__":
    asyncio.run(main())
