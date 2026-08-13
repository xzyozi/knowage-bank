---
title: "環境構築仕様書（プロジェクトセットアップ・依存関係管理仕様）"
document_type: "environment_spec"
version: "1.0"
created_at: "2026-06-14"
updated_at: "2026-08-13"
author: "開発チーム"
purpose: "Hatch / pyproject.toml および pip-tools によるプロジェクト環境構築・依存関係管理フローを明記するため"
related_documents:
  - "KNB-BD-001_基本設計書.md"
  - "KNB-TEST-001_テスト仕様書_単体テスト.md"
---

# 環境構築仕様書（プロジェクトセットアップ・依存関係管理仕様）
**Hatch / pyproject.toml / pip-tools 依存関係管理・開発環境構築**

| 項目 | 内容 |
| :--- | :--- |
| 文書番号 | KNB-ENV-001 |
| ドキュメント名 | 環境構築仕様書（プロジェクトセットアップ・依存関係管理仕様） |
| 版数 | Rev.1.0 (初版制定) |
| 改訂日 | 2026-08-13 |
| 作成日 | 2026-06-14 |
| 作成者 | 開発チーム |

---

本ドキュメントは、本プロジェクトの環境構築手順、`pyproject.toml` / Hatch による開発環境制御、ならびに `pip-tools` による依存関係管理フローをプログラム仕様の粒度で定義する。

## 1. プロジェクトセットアップガイド (Hatch版)

このプロジェクトは、依存関係と開発環境の管理に [Hatch](https://hatch.pypa.io/latest/) を使用します。プロジェクトルートにある `pyproject.toml` ファイルが、従来の `setup.py` の役割を置き換えます。

### 1.1 初回のみ必要な準備

作業を始める前に、Hatchをインストールする必要があります。この作業は一度だけで結構です。

```shell
pip install hatch
```

### 1.2 プロジェクトのセットアップ

プロジェクトの環境構築、すべての依存関係のインストール、Playwrightが必要とするブラウザのダウンロードを行うには、プロジェクトのルートディレクトリで以下のコマンドを実行してください。

```shell
hatch run setup
```

このコマンド一つで、以下の処理が自動的に実行されます。

1.  プロジェクト専用の仮想環境がなければ作成します。
2.  `pyproject.toml` に指定された、アプリケーション用および開発用のすべての依存関係をインストールします。
3.  `[tool.hatch.scripts]` に定義されたセットアップスクリプトを実行します。これには以下の処理が含まれます。
    *   `requirements.in` から `requirements.txt` を生成する。
    *   `requirements.txt` の内容と環境を完全に同期させる。
    *   Playwrightが必要とするブラウザドライバをインストールする。

### 1.3 仮想環境のアクティベート

プロジェクトの環境内で作業（例：スクリプトの手動実行など）を行いたい場合は、以下のコマンドで仮想環境のシェルに入ることができます。

```shell
hatch shell
```

### 1.4 テストの実行

このプロジェクトでは、`pytest` を使用してテストを実行するよう設定されています。以下のコマンドでテストスイート全体を実行できます。

```shell
hatch run test
```

---

## 2. 依存関係の管理フロー

このプロジェクトでは、Pythonの依存関係を管理するために `pip-tools` を使用します。
これにより、開発環境の再現性を高め、依存関係をクリーンに保ちます。

### 2.1 概要

依存関係は2つのファイルで管理されます。

-   `requirements.in`: プロジェクトが**直接**必要とするライブラリを記述するファイルです。**手で編集するのはこのファイルだけです。**
-   `requirements.txt`: `pip-compile`によって**自動生成**されるファイルです。プロジェクトの全依存ライブラリ（間接的なものも含む）とそのバージョンが固定されています。このファイルは手で編集しないでください。

### 2.2 新しいライブラリを追加する手順

1.  **`requirements.in` にライブラリを追加**
    -   プロジェクトのルートにある `requirements.in` ファイルを開き、追加したいライブラリ名を追記します。バージョンを指定することも可能ですが、通常は指定せずに最新の互換バージョンを自動で選択させます。

    ```
    # requirements.in

    flask
    requests
    # 新しいライブラリを追記
    new-library
    ```

2.  **`requirements.txt` を更新**
    -   ターミナルで以下のコマンドを実行し、`requirements.txt` を再生成します。

    ```bash
    pip-compile requirements.in
    ```

3.  **ライブラリのインストール**
    -   更新された `requirements.txt` を使して、ライブラリをインストールします。

    ```bash
    pip install -r requirements.txt
    ```

4.  **ファイルをコミット**
    -   変更された `requirements.in` と `requirements.txt` の両方をGitにコミットしてください。

### 2.3 新しい開発環境をセットアップする手順 (手動手続)

1.  **リポジトリをクローン**
    -   `git clone ...`

2.  **仮想環境の作成と有効化** (推奨)
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/macOS
    # .venv\Scripts\activate  # Windows
    ```

3.  **依存ライブラリのインストール**
    -   `requirements.txt` を使って、プロジェクトに必要な全てのライブラリをインストールします。

    ```bash
    pip install -r requirements.txt
    ```

4.  **初期セットアップの実行**
    -   データベースのマイグレーションや、`esbuild`のセットアップを行います。

    ```bash
    python setup.py
    ```

---

## 3. 改訂履歴 (Change Log)

| 版数 | 改訂日 | 変更者 | 変更内容・変更理由 (Why) |
| :--- | :--- | :--- | :--- |
| Rev.1.0 | 2026-08-13 | 開発チーム | TEMPLATEに準拠したドキュメント構造化およびフォーマット標準化（dependency_management.mdおよびtoml_project_setup.mdを統合・改訂） |
