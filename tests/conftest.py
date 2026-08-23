import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--run-integration", action="store_true", default=False, help="run integration tests"
    )
    parser.addoption(
        "--run-ollama", "--ollama", action="store_true", default=False, help="run tests requiring live Ollama server"
    )

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "ollama: mark test as requiring a running Ollama server")

def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration")
    run_ollama = config.getoption("--run-ollama")

    skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
    skip_ollama = pytest.mark.skip(reason="need --run-ollama / --ollama option to run")

    for item in items:
        if "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)
        if "ollama" in item.keywords and not run_ollama:
            item.add_marker(skip_ollama)
