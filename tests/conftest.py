"""Force mock mode + isolated data dir BEFORE app.config reads the env."""
import os
import tempfile

os.environ["GENESIS_MOCK"] = "1"
os.environ["GENESIS_DATA_DIR"] = tempfile.mkdtemp(prefix="genesis-grafana-test-")
os.environ.pop("GRAFANA_MCP_URL", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)

import pytest  # noqa: E402

from app.tools.grafana.mcp_client import mock_state  # noqa: E402


@pytest.fixture(autouse=True)
def reset_scenario():
    state = mock_state()
    state.remediated = False
    state.allow_improvement = True
    yield
    state.remediated = False
    state.allow_improvement = True
