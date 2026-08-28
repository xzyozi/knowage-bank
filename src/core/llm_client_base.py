#!/usr/bin/env python3
"""
tools/base/llm_client_base.py

他モデル（OpenAI, Ollama, llama-server, vLLM等）の呼び出しおよび JSON レスポンスパース処理を
汎用的に再利用可能にした独立クライアントモジュール。
特定のプロジェクト設定構造（config/models.json 等）に依存せず、引数による依存注入を基本とする。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger("tools.base.llm_client_base")


def extract_json_from_text(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    LLMが出力した生のテキストから JSON オブジェクトを抽出・デコードする汎用ユーティリティ関数。

    - 完全な JSON 文字列
    - マークダウンのコードブロック ```json ... ```
    - テキストの中に埋め込まれた JSON オブジェクト
    などを堅牢にパースする。

    Returns:
        デコードされた辞書オブジェクト。抽出・パース失敗時は None を返す。
    """
    if not raw_text or not raw_text.strip():
        return None

    # 1. 直接 json.loads を試行
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. 最初に出現する '{' からロバストにデコード
    start_idx = raw_text.find("{")
    if start_idx != -1:
        try:
            decoder = json.JSONDecoder()
            parsed, _ = decoder.raw_decode(raw_text[start_idx:])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


class BaseLLMClient:
    """
    OpenAI 互換 REST API (OpenAI, Ollama, llama-server, vLLM 等) と通信する
    再利用可能な LLM クライアント基盤クラス。

    Args:
        api_base: API のベース URL (例: "http://localhost:8080/v1")
        api_key: API キー (ローカルモデル等の場合はダミー文字列)
        default_timeout: リクエストのデフォルトタイムアウト時間(秒)
    """

    def __init__(self, api_base: str, api_key: str = "local", default_timeout: int = 300) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.default_timeout = default_timeout

    def completion(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        expect_json: bool = False,
        timeout: Optional[int] = None,
        extra_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        指定したモデルとプロンプトでテキスト生成リクエストを送信する。

        Args:
            model: 使用するモデル名 (例: "gemma-4-12b", "qwen2.5-coder")
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト
            temperature: 生成のランダム性
            max_tokens: 最大生成トークン数
            expect_json: True の場合、レスポンスから JSON オブジェクトを抽出して返す
            timeout: リクエスト個別のタイムアウト秒数
            extra_messages: 追加の対話履歴メッセージリスト
            **kwargs: OpenAI チャットコンプリーションに渡す追加引数

        Returns:
            - expect_json=False: {"raw": 生成テキスト}
            - expect_json=True: パースされた辞書オブジェクト (パース失敗時は {"raw": ..., "json_error": True})
        """
        request_timeout = timeout if timeout is not None else self.default_timeout

        messages = [{"role": "system", "content": system_prompt}]
        if extra_messages:
            messages.extend(extra_messages)
        messages.append({"role": "user", "content": user_prompt})

        completion_params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        completion_params.update(kwargs)

        client = OpenAI(base_url=self.api_base, api_key=self.api_key, timeout=request_timeout)

        try:
            logger.info(f"Sending completion request to '{self.api_base}' (model: '{model}')")
            response = client.chat.completions.create(**completion_params)
        except Exception as e:
            logger.error(f"LLM Client API Error ({self.api_base} / model: {model}): {e}")
            raise

        raw_output = response.choices[0].message.content or ""

        if not expect_json:
            return {"raw": raw_output}

        parsed_json = extract_json_from_text(raw_output)
        if parsed_json is not None:
            return parsed_json

        logger.warning(f"Failed to extract JSON from model response (raw length: {len(raw_output)})")
        return {"raw": raw_output, "json_error": True}
