import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.schemas.chat import ChatRequest


@pytest.fixture
def unconfigured_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MODEL_NAME", "")
    monkeypatch.setenv("MODEL_API_KEY", "")
    get_settings.cache_clear()
    yield app
    get_settings.cache_clear()


def test_status_is_available_without_api_key(unconfigured_app) -> None:
    with TestClient(unconfigured_app) as client:
        response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "configuration_required"
    assert payload["capabilities"]["short_term_memory"] == "memory"


def test_chat_explains_missing_model_configuration(unconfigured_app) -> None:
    with TestClient(unconfigured_app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "你好", "thread_id": "thread-1", "user_id": "user-1"},
        )

    assert response.status_code == 503
    assert "MODEL" in response.json()["detail"]


def test_chat_defaults_to_all_people() -> None:
    assert ChatRequest(message="你好").subject_id == "all"
