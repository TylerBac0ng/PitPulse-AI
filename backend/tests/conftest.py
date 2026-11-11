import os

# Tests never touch the network: real seasons fall back to the seeded demo dataset.
os.environ.setdefault("PITPULSE_OFFLINE", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.data.repository import repository  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "offline", True)
    repository.clear_memory()
    yield
    repository.clear_memory()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def demo(client):
    r = client.post(
        "/api/analysis/load",
        json={"season": "demo", "round": 1, "session": "R", "driver_a": "MOR", "driver_b": "COS"},
    )
    assert r.status_code == 200, r.text
    return r.json()
