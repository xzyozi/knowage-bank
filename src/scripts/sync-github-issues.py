import argparse
import asyncio
import os
import re
import subprocess
import sys
import uuid

# src/ を module 検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp import ClientSession
from mcp.client.sse import sse_client

from app import config
from app.article_builder import ArticleBuilder
from app.article_source_manager import save_article_source
from app.chatmodel import ChatModel
from app.issue_manager import IssueManager
from app.utils.logger import logger
from app.utils.markdown_validator import validate_html, validate_markdown

# 動的インポートでハイフン付きスクリプトを読み込む
script_dir = os.path.dirname(os.path.abspath(__file__))
sync_script_path = os.path.join(script_dir, "sync-article-dates.py")
spec = importlib_util_spec = None
try:
    import importlib.util

    spec = importlib.util.spec_from_file_location("sync_article_dates", sync_script_path)
    if spec is not None and spec.loader is not None:
        sync_article_dates = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_article_dates)
except Exception as e:
    logger.error(f"Failed to import sync-article-dates: {e}")


def repair_truncated_json(json_str: str) -> str:
    """途中で切れてしまったJSONを複数段階で修復してパース可能な状態にする"""
    json_str = json_str.strip()
    if not json_str:
        return json_str

    # ステップ1: 末尾が不完全なキー定義（値がない "key": のみ）で終わっている場合に null を補完
    # 例: ..."q": -> ..."q": null
    import re as _re

    # 末尾が `"key":` 形式で終わっている場合（値が欠損）
    json_str = _re.sub(r'"([^"]+)"\s*:\s*$', r'"\1": null', json_str.rstrip())

    # ステップ2: 末尾が `,` で終わっている場合は除去（不完全なリストの末尾カンマ）
    json_str = json_str.rstrip().rstrip(",")

    # ステップ3: 括弧とクォーテーションのスタック解析で不足している閉じ記号を追加
    in_string = False
    escaped = False
    stack = []
    i = 0

    while i < len(json_str):
        char = json_str[i]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            in_string = not in_string
        elif not in_string:
            if char in ("{", "["):
                stack.append(char)
            elif char in ("}", "]"):
                if stack:
                    top = stack[-1]
                    if (char == "}" and top == "{") or (char == "]" and top == "["):
                        stack.pop()
        i += 1

    # 文字列が閉じられていない場合はダブルクォートを補完
    if in_string:
        json_str += '"'

    # 残っているスタックの括弧を逆順に閉じる
    while stack:
        top = stack.pop()
        if top == "{":
            json_str += "}"
        elif top == "[":
            json_str += "]"

    return json_str


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
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True
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


async def process_single_issue(
    issue: dict, manager: IssueManager, git_commit_flag: bool = False, git_push: bool = False
) -> bool:
    issue_num = issue["number"]
    title = issue["title"]
    body = issue.get("body", "")

    attempt_id = str(uuid.uuid4())
    logger.info(f"🚀 Starting generation for Issue #{issue_num}: {title} (attempt: {attempt_id})")
    manager.update_issue_status(issue_num, "processing", attempt_id=attempt_id)

    try:
        model = ChatModel()

        # 1. LLMを用いてリサーチクエリを決定
        query_prompt = f"以下のGitHub Issueの内容に基づいて、技術的な詳細をWeb検索・リサーチするためのクエリ文（日本語で1文程度、検索キーワードの羅列でも可）を生成してください。余計な前置きや説明は完全に省き、検索クエリ文そのもののみを出力してください。\n\n【Issueタイトル】\n{title}\n\n【Issue本文】\n{body}"
        query_history = {
            "messages": [
                {
                    "role": "system",
                    "content": "あなたは与えられたIssueから最適な検索エンジン用のクエリ文を抽出するアシスタントです。",
                },
                {"role": "user", "content": query_prompt},
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
                        session.call_tool("run_deep_research", arguments={"query": research_query}), timeout=1800.0
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

        # 3. リサーチ結果を元にした Markdown 記事生成プロンプトの作成
        prompt = f"""
以下のリサーチ結果およびGitHub Issueの内容に基づいて、技術質問ノートに掲載するための標準的な Markdown ドキュメントを出力してください。

【リサーチインプット】
{research_text}

【Issueのタイトル】
{title}

【Issueの本文】
{body}

【記述フォーマットルール】
1. **YAML Frontmatter**:
   冒頭に必ず以下の形式で Frontmatter を記述してください。
   ```yaml
   ---
   title: "{title}"
   eyebrow: "AI > 開発ワークフロー"
   lead: "記事全体のポイントを1〜2段落でまとめたリード文"
   ---
   ```

2. **見出し構造**:
   - 本文の見出しは `##` (H2) および `###` (H3) のみを使用してください。
   - リサーチ結果から判明した仕様、具体的手順、他技術との比較など、論点ごとに最低 **4つ以上** の H2 セクションを作成してください。

3. **要点 (Key Points)**:
   - 記事冒頭付近に `## 要点` または `## まとめ` セクションを設け、箇条書き（`- `）で重要ポイントを抽出してください。

4. **Q&A (質問と回答)**:
   - 記事末尾付近に `## FAQ` または `## Q&A` セクションを作成し、以下のような形式で 4 つ以上の Q&A を含めてください。
     Q: 質問内容1
     A: 回答内容1

5. **参考文献 (References)**:
   - 記事末尾に参考文献セクションを設け、Markdown リンク `[タイトル](https://...)` の形式で URL を記載してください。

【出力時の重要制約】
- 返答は純粋な Markdown テキストのみを出力してください（JSONや「以下が記事です」などの不要な前置き文は含めないでください）。
- HTMLタグは使用せず、標準的な Markdown 構文（見出し、段落、リスト、コードフェンス ```）のみを使用してください。
"""
        history = {
            "messages": [
                {
                    "role": "system",
                    "content": "あなたは技術記事の Markdown ドキュメントを生成する優秀なAIアシスタントです。指示通りの Markdown 形式のみを出力してください。",
                },
                {"role": "user", "content": prompt},
            ]
        }

        logger.info("Requesting Markdown article generation from LocalLLM...")
        response = model.generate_response(history)
        raw_content = response.content if (response and response.content) else None
        if not raw_content and response and hasattr(response, "reasoning") and response.reasoning:
            logger.info("LocalLLM content was empty, but reasoning content was found. Using reasoning content.")
            raw_content = response.reasoning

        if not raw_content:
            raise Exception("Empty response from LocalLLM")

        markdown_text = raw_content.strip()

        # markdownコードブロックで全体が包まれている場合のクレンジング
        if markdown_text.startswith("```markdown") and markdown_text.endswith("```"):
            markdown_text = markdown_text[11:-3].strip()
        elif markdown_text.startswith("```md") and markdown_text.endswith("```"):
            markdown_text = markdown_text[5:-3].strip()

        # 3.5. 保存前検証 (Stage 3 / OUT-05, OUT-06)
        val_md = validate_markdown(markdown_text)
        if not val_md.is_valid:
            err_msg = f"[Stage 3] Markdown ValidationFailed: {'; '.join(val_md.errors)}"
            logger.error(f"❌ Markdown validation failed for Issue #{issue_num}: {err_msg}")
            manager.update_issue_status(issue_num, "failed", attempt_id=attempt_id, failure_reason=err_msg)
            return False

        # 4. Markdown 原本を data/article_sources/issue-<番号>.md に原子的書込みで保存 (OUT-03)
        source_filename = f"issue-{issue_num}.md"
        logger.info(f"Saving Markdown article source: {source_filename}...")
        save_article_source(issue_num, markdown_text)

        # 5. HTML記事の構築と保存 (OUT-04)
        builder = ArticleBuilder()
        filename = sanitize_filename(title, issue_num)

        logger.info(f"Building HTML from Markdown and saving to {filename}...")
        html_path = builder.save_article({"markdown_text": markdown_text}, filename)

        if not html_path or not os.path.exists(html_path):
            raise ValueError(f"save_article failed or returned invalid path for Issue #{issue_num}: {html_path}")

        # 5.5. 保存後検証 (Stage 5 / OUT-05, OUT-06)
        with open(html_path, "r", encoding="utf-8") as f:
            html_text = f.read()
        val_html = validate_html(html_text)
        if not val_html.is_valid:
            err_msg = f"[Stage 5] HTML ValidationFailed: {'; '.join(val_html.errors)}"
            logger.error(f"❌ HTML validation failed for Issue #{issue_num}: {err_msg}")
            manager.update_issue_status(issue_num, "failed", attempt_id=attempt_id, failure_reason=err_msg)
            return False

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

        # ステータスを完了に更新 (OUT-01)
        manager.update_issue_status(
            issue_num,
            "processed",
            article_file=filename,
            article_source_file=source_filename,
            index_synced=True,
            attempt_id=attempt_id,
        )
        logger.info(f"✅ Successfully processed Issue #{issue_num}!")
        return True

    except Exception as e:
        logger.exception(f"❌ Failed to process Issue #{issue_num}:")
        err_msg = f"[{type(e).__name__}] {str(e)}"
        manager.update_issue_status(issue_num, "failed", attempt_id=attempt_id, failure_reason=err_msg)
        return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sync GitHub Issues and generate articles.")
    parser.add_argument("--run-once", action="store_true", help="Run sync and process one issue, then exit.")
    parser.add_argument(
        "--interval", type=int, default=1800, help="Polling interval in seconds (default: 1800s / 30m)."
    )
    parser.add_argument(
        "--commit", action="store_true", help="Automatically git add and commit after generating articles."
    )
    parser.add_argument(
        "--push", action="store_true", help="Automatically git commit and push after generating articles."
    )
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
