#!/usr/bin/env python3
"""
tools/base/vram_manager.py

汎用的な VRAM 管理および LLM バックエンド排他制御・ライフサイクル管理モジュール。
プロジェクト特定のパスや設定構造に直接依存せず、引数経由の依存注入（Dependency Injection）を基本とすることで
高再利用性を実現するスタンドアロンな共通基盤。
"""

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import time
from typing import Any, BinaryIO, Dict, Generator, List, Protocol, Union
import urllib.error
import urllib.request


class Timeout(Exception):
    """ロック取得が指定時間内に完了しなかった場合の例外。"""


class FileLock:
    """WindowsとPOSIXで動作する、標準ライブラリのみのプロセス間ファイルロック。"""

    def __init__(self, lock_file: str, timeout: float) -> None:
        self.lock_file = lock_file
        self.timeout = timeout
        self._file: BinaryIO | None = None

    def acquire(self) -> None:
        deadline = time.monotonic() + self.timeout
        self._file = open(self.lock_file, "a+b")
        self._file.seek(0)
        if not self._file.read(1):
            self._file.write(b"\0")
            self._file.flush()

        while True:
            try:
                self._acquire_nonblocking()
                return
            except OSError as error:
                if time.monotonic() >= deadline:
                    self._file.close()
                    self._file = None
                    raise Timeout() from error
                time.sleep(0.1)

    def release(self) -> None:
        if self._file is None:
            return

        try:
            if os.name == "nt":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                flock = getattr(fcntl, "flock")
                flock(self._file.fileno(), getattr(fcntl, "LOCK_UN"))
        finally:
            self._file.close()
            self._file = None

    def _acquire_nonblocking(self) -> None:
        if self._file is None:
            raise RuntimeError("File lock is not initialized.")

        if os.name == "nt":
            import msvcrt

            self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            flock = getattr(fcntl, "flock")
            lock_flags = getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB")
            flock(self._file.fileno(), lock_flags)


logger = logging.getLogger("core.vram_manager")


class BackendAdapter(Protocol):
    """LLM バックエンド実行アダプタの抽象 Protocol インターフェース."""

    def execute(self, request: Dict[str, Any]) -> Any:
        """指定されたワークロードリクエストを実行する."""
        ...


class GpuLease:
    """
    GPU (VRAM) 資源の排他制御を管理する汎用アダプタ。

    filelock (OSネイティブロック) を用いることでプロセス異常終了時にも
    OSが自動的にロックを解放し、安全な排他利用を保証する。

    Args:
        lock_path: ロックファイルのパス (ファイルパスまたはディレクトリ+ファイル名)
        timeout: ロック取得のタイムアウト時間(秒)
    """

    def __init__(self, lock_path: Union[str, Path] = ".gpu_lease.lock", timeout: int = 60) -> None:
        self.lock_path = Path(lock_path).resolve()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.lock = FileLock(str(self.lock_path), timeout=timeout)

    def __enter__(self) -> "GpuLease":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def acquire(self) -> None:
        """GPUリースを取得する。取得できない場合は TimeoutError を送出する。"""
        try:
            logger.info(f"Waiting for GPU lease at '{self.lock_path}'...")
            self.lock.acquire()
            logger.info("GPU lease acquired.")
        except Timeout as e:
            logger.error(f"Failed to acquire GPU lease within {self.timeout}s.")
            raise TimeoutError(f"Failed to acquire GPU lease within {self.timeout} seconds.") from e

    def release(self) -> None:
        """GPUリースを解放する。"""
        try:
            self.lock.release()
            logger.info("GPU lease released.")
        except Exception as e:
            logger.error(f"Error releasing GPU lease: {e}")


class OllamaController:
    """
    Ollama バックエンドの VRAM およびモデル退避を管理するコントローラ。

    Args:
        management_endpoint: Ollama の管理エンドポイント URL (例: "http://localhost:11434")
    """

    def __init__(self, management_endpoint: str = "http://localhost:11434") -> None:
        self.base_url = self._normalize_url(management_endpoint)

    @staticmethod
    def _normalize_url(endpoint: str) -> str:
        if endpoint.endswith("/v1") or endpoint.endswith("/v1/"):
            return endpoint.rsplit("/v1", 1)[0].rstrip("/")
        return endpoint.rstrip("/")

    def list_loaded_models(self) -> List[str]:
        """現在 Ollama の VRAM 上にロードされているモデル名のリストを取得する。"""
        ps_url = f"{self.base_url}/api/ps"
        try:
            req = urllib.request.urlopen(ps_url, timeout=2)
            if req.getcode() == 200:
                data = json.loads(req.read().decode("utf-8"))
                return [m.get("name") for m in data.get("models", []) if m.get("name")]
        except urllib.error.URLError as e:
            logger.warning(f"Ollama endpoint unreachable at {ps_url}: {e}")
            raise
        return []

    def unload_model(self, model_name: str) -> None:
        """指定したモデルの VRAM ロードを解除する。"""
        gen_url = f"{self.base_url}/api/generate"
        logger.info(f"Unloading Ollama model: {model_name}")
        unload_req = urllib.request.Request(
            gen_url,
            data=json.dumps({"model": model_name, "keep_alive": 0}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(unload_req, timeout=5)

    def wait_until_unloaded(self, timeout: float = 10.0) -> None:
        """すべてのモデルがアンロードされるまで待機する。"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.list_loaded_models():
                return
            time.sleep(1)
        raise RuntimeError("Failed to unload Ollama models within timeout. VRAM might not be freed.")

    def unload_all_models(self, ignore_unreachable: bool = True) -> None:
        """
        Ollama にロードされているすべてのモデルをアンロードし、VRAM を解放する。

        Args:
            ignore_unreachable: Trueの場合、Ollamaサービスが停止して接続できないエラーを無視する
        """
        try:
            loaded_models = self.list_loaded_models()
            for model in loaded_models:
                self.unload_model(model)
            if loaded_models:
                self.wait_until_unloaded()
        except urllib.error.URLError as e:
            if ignore_unreachable:
                logger.info(f"Ollama is unreachable ({e}). Assuming VRAM is already free.")
            else:
                raise


class LlamaServerManager:
    """
    llama-server (llama.cpp) の動的プロセス管理および VRAM ライフサイクル制御クラス。
    """

    def __init__(
        self, executable: str = "llama-server.exe", host: str = "127.0.0.1", port: int = 8080, health_timeout: int = 120
    ) -> None:
        self.executable = executable
        self.host = host
        self.port = port
        self.health_timeout = health_timeout

    @contextmanager
    def run_server(self, cmd_args: List[str]) -> Generator[subprocess.Popen, None, None]:
        """
        指定された引数で llama-server をバックグラウンド起動し、
        ブロックを抜ける際に終了処理および VRAM / ポート解放の確認監査を行う。

        Args:
            cmd_args: llama-server に渡すコマンドライン引数のリスト
        """
        full_cmd = [self.executable] + cmd_args

        logger.info(f"Starting {self.executable} on {self.host}:{self.port}...")
        logger.debug(f"Command: {' '.join(full_cmd)}")

        process = subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        health_url = f"http://{self.host}:{self.port}/health"
        ready = False
        start_time = time.time()

        while time.time() - start_time < self.health_timeout:
            try:
                req = urllib.request.urlopen(health_url, timeout=2)
                if req.getcode() == 200:
                    ready = True
                    logger.info(f"Server is ready at {health_url}")
                    break
            except (urllib.error.URLError, ConnectionResetError):
                pass

            if process.poll() is not None:
                logger.error(f"Process terminated unexpectedly with exit code {process.returncode}")
                raise RuntimeError(f"Server process failed to start (exit code {process.returncode}).")

            time.sleep(2)

        if not ready:
            process.terminate()
            raise TimeoutError(f"Server did not become healthy within {self.health_timeout} seconds.")

        try:
            yield process
        finally:
            logger.info("Terminating server process and freeing VRAM...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Server process did not terminate gracefully, forcing kill...")
                process.kill()
                process.wait()

            # ポート解放を監査
            logger.info("Auditing port release...")
            port_freed = False
            for _ in range(10):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    res = s.connect_ex((self.host, self.port))
                    if res != 0:
                        port_freed = True
                        break
                time.sleep(1)

            if not port_freed:
                raise RuntimeError(f"Server failed to free port {self.port} after termination.")

            logger.info("VRAM and port release confirmed.")
