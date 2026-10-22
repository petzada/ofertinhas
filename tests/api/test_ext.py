import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ofertinhas import db
from ofertinhas.api.app import ApiState, create_app
from ofertinhas.config import load_config
from ofertinhas.models import CandidateState
from ofertinhas.settings import Settings

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "portal"
TOKEN = "tok"
H = {"X-Ofertinhas-Token": TOKEN}
NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)  # 12:00 em São Paulo


class Env:
    def __init__(self, tmp_path, tag="minhatag"):
        env = {"OFERTINHAS_DATA_DIR": str(tmp_path), "EXTENSION_TOKEN": TOKEN}
        if tag:
            env["ML_AFFILIATE_TAG"] = tag
        self.now = NOW
        self.sent: list[str] = []

        async def notify(text):
            self.sent.append(text)

        self.state = ApiState(
            settings=Settings.from_env(env),
            conn=db.connect(":memory:"),
            cfg=load_config(ROOT / "config.example.yaml"),
            notify=notify,
            clock=lambda: self.now,
        )
        self.client = TestClient(create_app(self.state))

    @property
    def conn(self):
        return self.state.conn


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def raw_payload(name):
    data = fixture(name)
    return {"url": data["request"]["url"], "request_body": data["request"]["body"],
            "status": 200, "body": data["response"]["body"]}


def test_routes_require_token(env):
    assert env.client.get("/ext/config").status_code == 401
    assert env.client.post("/ext/raw", json={}).status_code == 401


def test_config_lists_niche_categories_and_rhythm(env):
    cfg = env.client.get("/ext/config", headers=H).json()
    assert cfg["paused"] is False
    assert cfg["window"] == ["08:00", "23:00"]
    assert cfg["collect_every_min"] == 20 and cfg["pages_per_category"] == 3
    assert cfg["categories"][0] == {"id": "MLB1574", "name": "Casa, Móveis e Decoração"}
    assert cfg["portal_url"].startswith("https://www.mercadolivre.com.br/afiliados/hub")
    assert cfg["search_url"].endswith("/affiliate-program/api/hub/search?is_affiliate=true"
                                      "&device=desktop")


def test_config_skips_paused_niche_categories(env):
    db.set_niche_override(env.conn, "casa", "paused", True)
    ids = [c["id"] for c in env.client.get("/ext/config", headers=H).json()["categories"]]
    assert "MLB1574" not in ids and "MLB1648" in ids


def test_raw_ingests_and_ranks(env):
    r = env.client.post("/ext/raw", headers=H,
                        json=raw_payload("hub-search-categoria-games-internacional.json"))
    assert r.status_code == 200
    out = r.json()
    assert out["parsed"] == 18 and out["new"] == 18
    assert db.get_offer(env.conn, "MLB5338583985").category_path == ("MLB1144",)
    # contagem por estado igual ao que ficou no banco
    assert out["routed"] == db.count_candidates(env.conn)


def test_raw_twice_does_not_duplicate(env):
    payload = raw_payload("hub-search-categoria-bebes.json")
    env.client.post("/ext/raw", headers=H, json=payload)
    second = env.client.post("/ext/raw", headers=H, json=payload).json()
    assert second["new"] == 0 and second["parsed"] == 18
    assert env.conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 18


def test_raw_unknown_format_is_saved_and_reported_once_per_hour(env, tmp_path):
    payload = {"url": "https://www.mercadolivre.com.br/affiliate-program/api/hub/search",
               "request_body": {}, "status": 200, "body": {"novo": "formato"}}
    out = env.client.post("/ext/raw", headers=H, json=payload).json()
    assert out == {"parsed": 0, "unknown": True}
    assert len(list((tmp_path / "unparsed").glob("*.json"))) == 1
    env.client.post("/ext/raw", headers=H, json=payload)
    assert len(env.sent) == 1


def test_raw_ignores_other_urls(env):
    out = env.client.post("/ext/raw", headers=H,
                          json={"url": "https://www.mercadolivre.com.br/x", "body": {}}).json()
    assert out == {"ignored": True}


def approve_one(env):
    env.client.post("/ext/raw", headers=H, json=raw_payload("hub-search-geral-offset18.json"))
    with env.conn:
        env.conn.execute(
            "INSERT OR REPLACE INTO candidates VALUES "
            "('MLB7818802816','casa','approved',90,'{}',87.2,?,NULL,NULL,NULL)",
            (NOW.isoformat(),),
        )


def test_link_request_and_success(env):
    approve_one(env)
    req = env.client.get("/ext/link-requests", headers=H).json()["request"]
    assert req["mlb_id"] == "MLB7818802816" and req["body"]["tag"] == "minhatag"

    response = fixture("create-link.json")["response"]["body"]
    response["urls"][0]["origin_url"] = req["body"]["urls"][0]
    out = env.client.post("/ext/links", headers=H,
                          json={"mlb_id": "MLB7818802816", "response": response}).json()
    assert out == {"ok": True}
    assert db.get_offer(env.conn, "MLB7818802816").affiliate_link == "https://meli.la/33zyUam"
    assert db.get_candidate(env.conn, "MLB7818802816", "casa").state is CandidateState.LINKED


def test_link_request_empty(env):
    assert env.client.get("/ext/link-requests", headers=H).json() == {"request": None}


def test_link_request_without_tag_warns_admin(tmp_path):
    env = Env(tmp_path, tag=None)
    approve_one(env)
    out = env.client.get("/ext/link-requests", headers=H).json()
    assert out["request"] is None and "ML_AFFILIATE_TAG" in out["error"]
    assert len(env.sent) == 1


def test_three_link_failures_notify_admin(env):
    approve_one(env)
    for _ in range(3):
        env.client.post("/ext/links", headers=H, json={"mlb_id": "MLB7818802816", "error": "500"})
    assert db.get_candidate(env.conn, "MLB7818802816", "casa").state is (
        CandidateState.LINK_FAILED
    )
    assert any("MLB7818802816" in m for m in env.sent)


def test_alert_pauses_and_resume_clears(env):
    out = env.client.post("/ext/alert", headers=H,
                          json={"reason": "login", "url": "https://x/login"}).json()
    assert out == {"paused": True}
    cfg = env.client.get("/ext/config", headers=H).json()
    assert cfg["paused"] is True and cfg["pause_reason"] == "login"
    assert len(env.sent) == 1
    env.client.post("/ext/alert", headers=H, json={"reason": "login"})
    assert len(env.sent) == 1  # mesmo motivo em 30 min: sem aviso repetido
    env.now = NOW + timedelta(minutes=31)
    env.client.post("/ext/alert", headers=H, json={"reason": "login"})
    assert len(env.sent) == 2
    assert env.client.post("/ext/resume", headers=H).json() == {"paused": False}
    assert env.client.get("/ext/config", headers=H).json()["paused"] is False
