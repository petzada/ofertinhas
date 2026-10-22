from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ofertinhas import db
from ofertinhas.api.app import ApiState, create_app
from ofertinhas.config import load_config
from ofertinhas.settings import Settings

TOKEN = "token-de-teste"
EXAMPLE = Path(__file__).parents[2] / "config.example.yaml"


async def no_notify(text: str) -> None:
    pass


@pytest.fixture
def client(tmp_path):
    settings = Settings.from_env({"OFERTINHAS_DATA_DIR": str(tmp_path), "EXTENSION_TOKEN": TOKEN})
    state = ApiState(
        settings=settings,
        conn=db.connect(":memory:"),
        cfg=load_config(EXAMPLE),
        notify=no_notify,
    )
    return TestClient(create_app(state))


def test_health_with_token(client):
    r = client.get("/health", headers={"X-Ofertinhas-Token": TOKEN})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_missing_token_is_401(client):
    assert client.get("/health").status_code == 401


def test_wrong_token_is_401(client):
    assert client.get("/health", headers={"X-Ofertinhas-Token": "x"}).status_code == 401


def test_without_configured_token_everything_is_401(tmp_path):
    state = ApiState(
        settings=Settings.from_env({"OFERTINHAS_DATA_DIR": str(tmp_path)}),
        conn=db.connect(":memory:"),
        cfg=load_config(EXAMPLE),
        notify=no_notify,
    )
    c = TestClient(create_app(state))
    assert c.get("/health", headers={"X-Ofertinhas-Token": ""}).status_code == 401


def test_docs_are_disabled(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
