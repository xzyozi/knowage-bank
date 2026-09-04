# Knowage Bank

GitHub Issueとブラウザの検索履歴から技術ナレッジを収集し、Markdown原本・静的HTML記事・インデックスを管理するPythonツールです。

## 主な機能

- GitHub Issueを入力に、Markdown原本とHTML記事を生成・同期する
- 保存前後の検証、原子的書込み、Issue処理状態の記録を行う
- Chrome、Edge、Firefoxの検索履歴をセッション化し、ナレッジ候補をIssueへルーティングする

## 前提条件

- Python 3.10以上
- [uv](https://docs.astral.sh/uv/)
- 記事同期を実行する場合: OllamaまたはLiteLLM互換のローカルLLM
- Deep Researchを利用する場合: MCP SSEサーバー（未接続時はIssue本文へフォールバック）

## セットアップ

```powershell
Copy-Item .env.sample .env
uv sync --all-extras
```

`.env`には対象リポジトリ、LLM接続先、必要に応じてGitHubトークンとGemini APIキーを設定します。秘密情報を含む`.env`はGitへコミットしません。

## 安全な動作確認

実行前に、対象経路で必要な設定と依存を副作用なく確認します。

```powershell
uv run python src/scripts/preflight-check.py --target issue-sync
```

ブラウザ履歴を外部サービスへ書き込まず確認します。

```powershell
uv run python src/scripts/run-personal-knowledge-collector.py --backend local --no-gemini --dry-run
```

GitHub Issueから記事を1件だけ同期する場合は、必要な環境設定と外部サービスを準備してから実行します。

```powershell
uv run python src/scripts/sync-github-issues.py --run-once
```

## テストと品質確認

```powershell
uv run pytest
uv run pytest --run-integration tests/test_output_sync_integration.py
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

設計・運用上の制約は[`docs/`](docs/)を参照してください。