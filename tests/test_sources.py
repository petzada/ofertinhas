"""Amazon/Shopee no mesmo fluxo do Mercado Livre: regra por loja, link pronto, cota e legenda."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ofertinhas import db
from ofertinhas.api.app import ApiState, create_app
from ofertinhas.config import load_config_text
from ofertinhas.models import Offer
from ofertinhas.pipeline import store_note
from ofertinhas.publisher.publish import full_sources
from ofertinhas.settings import Settings
from ofertinhas.sources import make_id, source_of

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 11, 5, 15, tzinfo=UTC)  # 12h em SP
H = {"X-Ofertinhas-Token": "tok"}
CFG = """
multi_niche: true
defaults:
  rules:
    auto: {min_discount_pct: 39, min_commission_pct: 19}
    review: {min_discount_pct: 30, min_commission_pct: 15}
    amazon:
      auto: {min_discount_pct: 30}
      review: {min_discount_pct: 20}
niches:
  mulher: {categories: [MLB1246, MLB1574], telegram_chat_id: -100}
sources:
  amazon: {tag: ofertaderainh-20, max_share: 0.4}
"""


async def ignore(text):
    pass


@pytest.fixture
def client(tmp_path):
    state = ApiState(
        settings=Settings.from_env(
            {"OFERTINHAS_DATA_DIR": str(tmp_path), "EXTENSION_TOKEN": "tok"}
        ),
        conn=db.connect(":memory:"),
        cfg=load_config_text(CFG),
        notify=ignore,
        clock=lambda: NOW,
    )
    db.migrate(state.conn)
    return TestClient(create_app(state)), state


def test_ids_and_sources():
    assert make_id("amazon", "B0X") == "AMZ-B0X" and source_of("AMZ-B0X") == "amazon"
    assert source_of("SHP-123") == "shopee" and source_of("MLB123") == "ml"
    with pytest.raises(ValueError):
        make_id("shopee", "1:2")


def test_amazon_round_trip_uses_own_rules_and_skips_create_link(client):
    c, state = client
    cfg = c.get("/ext/config?purpose=collect", headers=H).json()["amazon"]
    assert len(cfg["requests"]) == 6  # Beleza, Casa e Cozinha, 2 páginas cada
    assert c.get("/ext/config?purpose=collect", headers=H).json()["amazon"] is None  # a cada 2 h
    body = json.loads((ROOT / "tests/fixtures/amazon/deals.json").read_text(encoding="utf-8"))
    req = cfg["requests"][0]
    out = c.post(
        "/ext/raw",
        headers=H,
        json={
            "url": req["url"],
            "status": 200,
            "body": body,
            "request_body": {"department": req["department"]},
        },
    )
    assert out.json()["parsed"] == 2
    dove = db.candidates_for_offer(state.conn, "AMZ-B0DC74428B")
    # 36% de desconto e comissão 4%: pela regra do ML iria ao lixo; pela da Amazon, é automática
    assert [x.state.value for x in dove] == ["approved"]
    assert db.get_offer(state.conn, "AMZ-B0DC74428B").affiliate_link.endswith(
        "tag=ofertaderainh-20"
    )
    assert c.get("/ext/link-requests", headers=H).json().get("request") is None


def test_full_sources_pushes_amazon_back_after_its_share(client):
    _, state = client
    for i, mlb in enumerate(["MLB1", "AMZ-A", "AMZ-B"]):
        db.record_post(
            state.conn,
            mlb_id=mlb,
            niche="mulher",
            channel="telegram",
            chat="-100",
            status="sent",
            sent_at=NOW - timedelta(minutes=10 * (i + 1)),
        )
    assert full_sources(state.conn, state.cfg, "-100", NOW) == {"amazon"}  # 2/3 ≥ 40%
    assert full_sources(state.conn, state.cfg, "outro", NOW) == set()


def test_store_note_only_outside_ml():
    base = dict(title="x", price=10, commission_pct=5, category_path=(), permalink="p")
    assert store_note(Offer(mlb_id="MLB1", **base), NOW) == ""
    amazon = Offer(mlb_id="AMZ-B1", last_seen_at=NOW, **base)
    assert store_note(amazon, NOW) == "\n\n🛒 Na Amazon • preço visto às 12:00, pode mudar"
    assert store_note(Offer(mlb_id="SHP-9", **base), NOW) == "\n\n🛒 Na Shopee"
