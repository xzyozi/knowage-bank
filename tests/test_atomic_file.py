"""atomic_file.py の単体テスト。"""

import os
from typing import Any
from unittest.mock import patch

import pytest

from app.utils.atomic_file import atomic_write_json, atomic_write_text


def test_atomic_write_text_success(tmp_path: Any) -> None:
    """テキスト原子的書き込みの正常系テスト"""
    file_path = os.path.join(tmp_path, "sub", "test.txt")
    content = "Hello, World!\n"

    atomic_write_text(file_path, content)

    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        read_data = f.read()
    assert read_data == content
    assert not os.path.exists(f"{file_path}.tmp")


def test_atomic_write_json_success(tmp_path: Any) -> None:
    """JSON原子的書き込みの正常系テスト"""
    file_path = os.path.join(tmp_path, "data.json")
    data = {"name": "test", "val": 123}

    atomic_write_json(file_path, data)

    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert '"name": "test"' in content
    assert not os.path.exists(f"{file_path}.tmp")


def test_atomic_write_text_preserves_original_on_failure(tmp_path: Any) -> None:
    """書込み失敗時に元のファイルが保護され一時ファイルが削除されるテスト"""
    file_path = os.path.join(tmp_path, "original.txt")
    original_content = "Original Content"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(original_content)

    # os.replace で例外を発生させる
    with patch("os.replace", side_effect=OSError("Replace failed")):
        with pytest.raises(OSError, match="Replace failed"):
            atomic_write_text(file_path, "New Broken Content")

    # 元のファイルが変更されず残っていること
    with open(file_path, "r", encoding="utf-8") as f:
        assert f.read() == original_content

    # .tmp 一時ファイルが綺麗に削除されていること
    assert not os.path.exists(f"{file_path}.tmp")
