"""article_source_manager.py の単体テスト。"""

import os
from typing import Any

import pytest

from app.article_source_manager import (
    load_article_source,
    rebuild_article_from_source,
    save_article_source,
)


def test_save_and_load_article_source(tmp_path: Any) -> None:
    """Markdown原本の保存および読み込みの正常系テスト"""
    source_dir = str(tmp_path)
    issue_number = 42
    markdown_content = "---\ntitle: テスト記事\neyebrow: 技術ノート\n---\n\n## 概要\nテスト本文"

    saved_path = save_article_source(issue_number, markdown_content, source_dir=source_dir)
    assert os.path.exists(saved_path)
    assert os.path.basename(saved_path) == "issue-42.md"

    loaded_content = load_article_source(issue_number, source_dir=source_dir)
    assert loaded_content == markdown_content


def test_load_article_source_file_not_found(tmp_path: Any) -> None:
    """存在しない原本ファイルを読み込もうとした場合に FileNotFoundError が発生すること"""
    source_dir = str(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_article_source(999, source_dir=source_dir)


def test_rebuild_article_from_source(tmp_path: Any) -> None:
    """保存済み Markdown 原本から外部LLM呼び出しなしで HTML が生成されるテスト"""
    source_dir = str(tmp_path)
    issue_number = 100
    markdown_content = (
        "---\ntitle: 再生成テスト記事\neyebrow: 開発 > バックエンド\n---\n\n"
        "## 要点\n- 要点1\n- 要点2\n\n"
        "## 本文\n原本から再生成されたテキスト"
    )

    save_article_source(issue_number, markdown_content, source_dir=source_dir)

    output_filename = "issue-100-rebuilt.html"
    # rebuild_article_from_source を呼び出し
    output_path = rebuild_article_from_source(
        issue_number, output_filename, source_dir=source_dir
    )

    assert os.path.exists(output_path)
    with open(output_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    assert "再生成テスト記事" in html_content
    assert "原本から再生成されたテキスト" in html_content


def test_save_article_source_verify_readback_mismatch(tmp_path: Any) -> None:
    """原本保存後の再読込内容が一致しない場合、ValueError が発生すること (OUT-03)"""
    source_dir = str(tmp_path)
    issue_number = 77
    markdown_content = "---\ntitle: 不一致テスト\n---\n\n本文"

    from app.article_source_manager import atomic_write_text
    original_atomic_write = atomic_write_text

    def tamper_atomic_write(file_path: str, content: str) -> None:
        original_atomic_write(file_path, content)
        # 書き込み後にファイルの中身を書き換えて改ざん状態を再現
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("---\ntitle: 壊れた内容\n---")

    from unittest.mock import patch

    with patch("app.article_source_manager.atomic_write_text", side_effect=tamper_atomic_write):
        with pytest.raises(ValueError, match="Saved article source content mismatch"):
            save_article_source(issue_number, markdown_content, source_dir=source_dir)


