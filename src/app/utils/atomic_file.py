"""原子的書込み（Atomic Write）モジュール。

ファイル操作の途中でプロセス中断や失敗が発生しても既存ファイルを破損させないため、
同一ディレクトリに一時ファイルを作成し、アトミックなファイル置換 (os.replace) を行う。
"""

import json
import os
from typing import Any

from app.utils.logger import logger


def atomic_write_text(file_path: str, content: str, encoding: str = "utf-8") -> None:
    """テキストデータを原子的 (Atomic) に指定パスに書き込む。"""
    dir_name = os.path.dirname(file_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    temp_path = f"{file_path}.tmp"

    try:
        with open(temp_path, "w", encoding=encoding, newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, file_path)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as clean_err:
                logger.warning(f"Failed to clean up temporary file {temp_path}: {clean_err}")
        logger.error(f"Atomic write text failed for {file_path}: {e}")
        raise


def atomic_write_json(
    file_path: str,
    data: Any,
    indent: int = 2,
    ensure_ascii: bool = False,
    encoding: str = "utf-8",
) -> None:
    """JSON データを原子的 (Atomic) に指定パスに書き込む。"""
    json_str = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(file_path, json_str + "\n", encoding=encoding)
