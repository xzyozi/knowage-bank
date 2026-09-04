---
title: "環境構築仕様書（プロジェクトセットアップ・依存関係管理仕様）"
document_type: "environment_spec"
version: "1.1"
created_at: "2026-06-14"
updated_at: "2026-09-04"
author: "開発チーム"
purpose: "uv、pyproject.toml、uv.lockおよび環境変数による再現可能な開発環境の構築手順を定義する"
related_documents:
  - "../design/KNB-BD-001_基本設計書.md"
  - "../test/KNB-TEST-001_テスト仕様書_単体テスト.md"
---

# 環境構築仕様書（プロジェクトセットアップ・依存関係管理仕様）

| 項目     | 内容        |
| :------- | :---------- |
| 文書番号 | KNB-ENV-001 |
| 版数     | Rev.1.1     |
| 改訂日   | 2026-09-04  |

本プロジェクトは、Python依存関係と仮想環境の管理に`uv`を使用する。依存関係の正本は`pyproject.toml`、解決済みバージョンの正本は`uv.lock`とする。Hatch、pip-tools、`requirements.txt`、`setup.py`は使用しない。

## 1. 前提条件

- Python 3.10以上
- `uv`
- GitHub Issue同期を実行する場合は、OllamaまたはLiteLLM互換のLLM接続先
- Deep Researchを使用する場合は、MCP SSEサーバー
- Geminiを使用する場合は、Gemini APIキー

## 2. 初期セットアップ

プロジェクトルートで次を実行する。

```powershell
Copy-Item .env.sample .env
uv sync --all-extras
```

`.env`はローカル環境専用の設定ファイルであり、認証情報を含み得るためGitへコミットしない。依存関係を変更する場合は`pyproject.toml`を更新し、`uv lock`で`uv.lock`を更新する。

## 3. 環境変数

| 変数                                | 用途                                  | 必須条件                           |
| :---------------------------------- | :------------------------------------ | :--------------------------------- |
| `OLLAMA_BASE_URL`                   | OllamaまたはLiteLLM互換エンドポイント | 記事同期時                         |
| `KNOWAGE_BANK_MODEL`                | 使用するLLMモデル                     | 記事同期時                         |
| `KNOWAGE_BANK_GITHUB_REPOSITORY`    | Issue同期対象の`owner/repository`     | GitHub同期時                       |
| `KNOWAGE_BANK_GITHUB_TOKEN`         | GitHub API認証                        | 非公開リポジトリ・レート制限回避時 |
| `KNOWAGE_BANK_DEEPRESEARCH_SSE_URL` | Deep Research MCP SSE URL             | Deep Research使用時                |
| `GEMINI_API_KEY`                    | Geminiによる意図判定・Embedding       | Gemini使用時                       |

## 4. 安全な動作確認

実行前に、対象経路で必要な設定と依存を副作用なく確認する。

```powershell
uv run python src/scripts/preflight-check.py --target issue-sync
```

ブラウザ履歴を外部サービスへ書き込まずに、ブラウザ履歴の収集・選定経路を確認する。

```powershell
uv run python src/scripts/run-personal-knowledge-collector.py --backend local --no-gemini --dry-run
```

GitHub Issueを1件だけ処理する場合は、必要な環境変数、LLM接続先、必要に応じてMCP SSEサーバーを準備してから実行する。

```powershell
uv run python src/scripts/sync-github-issues.py --run-once
```

## 5. 検証コマンド

```powershell
uv run pytest
uv run pytest --run-integration tests/test_output_sync_integration.py
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

通常の`pytest`は`integration`マーカー付きテストをスキップする。統合テストは`--run-integration`を明示して実行する。

## 6. 改訂履歴

| 版数    | 改訂日     | 変更内容                                                    |
| :------ | :--------- | :---------------------------------------------------------- |
| Rev.1.0 | 2026-08-13 | Hatch・pip-toolsを前提とした初版。                          |
| Rev.1.1 | 2026-09-04 | 現行のuv、uv.lock、環境変数、動作確認・検証コマンドへ更新。 |