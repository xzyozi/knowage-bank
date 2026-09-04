"""Knowage Bankの実行前設定を診断するCLI。"""

import argparse
import json
import os
import sys
from typing import cast

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.preflight import PreflightTarget, collect_preflight, has_errors


def main() -> int:
    """診断結果を表示し、不足があれば終了コード1を返す。"""
    parser = argparse.ArgumentParser(description="Knowage Bankの実行前設定を診断します。")
    parser.add_argument(
        "--target",
        choices=("issue-sync", "personal-knowledge"),
        default="issue-sync",
        help="診断対象の実行経路（既定: issue-sync）",
    )
    parser.add_argument("--json", action="store_true", help="診断結果をJSONで出力する")
    args = parser.parse_args()

    checks = collect_preflight(cast(PreflightTarget, args.target))
    if args.json:
        print(
            json.dumps(
                [{"name": check.name, "is_error": check.is_error, "message": check.message} for check in checks],
                ensure_ascii=False,
            )
        )
    else:
        for check in checks:
            status = "ERROR" if check.is_error else "OK"
            print(f"[{status}] {check.name}: {check.message}")
    return 1 if has_errors(checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
