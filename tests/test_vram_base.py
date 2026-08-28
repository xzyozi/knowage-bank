from typing import Any

"""
tests/test_vram_base.py

tools.base.vram_manager モジュールのユニットテスト。
"""

import os
import tempfile
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from tools.base import BackendAdapter, GpuLease, LlamaServerManager, OllamaController


def test_gpu_lease_acquire_and_release(tmp_path: Any) -> None:
    lock_file = tmp_path / "test_gpu.lock"
    lease = GpuLease(lock_path=lock_file, timeout=5)

    with lease:
        assert lock_file.exists()

    # Lock file is created on filesystem, lease released without exception


def test_ollama_controller_normalize_url() -> None:
    ctrl1 = OllamaController("http://localhost:11434/v1")
    assert ctrl1.base_url == "http://localhost:11434"

    ctrl2 = OllamaController("http://localhost:11434/v1/")
    assert ctrl2.base_url == "http://localhost:11434"

    ctrl3 = OllamaController("http://localhost:11434/")
    assert ctrl3.base_url == "http://localhost:11434"


@patch("urllib.request.urlopen")
def test_ollama_controller_unload_all_models_unreachable(mock_urlopen: Any) -> None:
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
    ctrl = OllamaController("http://localhost:11434")

    # Should ignore error when ignore_unreachable is True
    ctrl.unload_all_models(ignore_unreachable=True)

    # Should raise error when ignore_unreachable is False
    with pytest.raises(urllib.error.URLError):
        ctrl.unload_all_models(ignore_unreachable=False)


@patch("socket.socket")
@patch("urllib.request.urlopen")
@patch("subprocess.Popen")
def test_llama_server_manager_run_server(mock_popen: Any, mock_urlopen: Any, mock_socket: Any, tmp_path: Any) -> None:
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.return_value = 0
    mock_popen.return_value = mock_proc

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_urlopen.return_value = mock_resp

    # Mock socket connect_ex returning non-zero (port freed)
    mock_sock_inst = MagicMock()
    mock_sock_inst.connect_ex.return_value = 1  # 1 = Connection refused (port is free)
    mock_socket.return_value.__enter__.return_value = mock_sock_inst

    manager = LlamaServerManager(executable="llama-server.exe", port=8080, health_timeout=5)

    cmd_args = ["-m", "model.gguf", "-c", "2048"]
    with manager.run_server(cmd_args) as proc:
        assert proc == mock_proc

    mock_popen.assert_called_once()
    mock_proc.terminate.assert_called_once()
