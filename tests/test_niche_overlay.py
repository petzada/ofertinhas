"""Telegram com todas as ofertas e um grupo de WhatsApp só com um nicho fino (noivas)."""

from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.config import load_config_text
from ofertinhas.models import CandidateState, Offer
from ofertinhas.pipeline import score_and_route
from ofertinhas.preview import niche_preview

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
S = CandidateState
CFG = load_config_text("""
multi_niche: true
whatsapp_enabled: true
defaults:
  rules:
    auto: {min_discount_pct: 39, min_commission_pct: 19, strict: true}
    review: {min_discount_pct: 30, min_commission_pct: 15}
niches:
  casa:
    categories: [MLB1574]
    telegram_chat_id: -100
  beleza:
    categories: [MLB1246]
    telegram_chat_id: -100
  noivas:
    categories: [MLB1574, MLB1246]
    whatsapp_group_jid: "120363000000000001@g.us"
    filters:
      required_keywords: [jogo de cama, panela*, maquiagem, batom]
      blocked_keywords: [usado, masculino]
""")


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def add(conn, mlb_id, title, category="MLB1574", now=NOW):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title=title, price=50, original_price=100, commission_pct=25,
        category_path=(category,), permalink="https://x", collected_at=now, rating=4.8,
    ), now=now)


def niches_of(conn, mlb_id):
    return sorted(c.niche for c in db.candidates_for_offer(conn, mlb_id))


def test_telegram_gets_everything_and_whatsapp_only_the_niche(conn):
    add(conn, "MLB1", "Jogo de Panelas Inox 5 Peças")
    add(conn, "MLB2", "Lixeira Inox 30 Litros")
    add(conn, "MLB3", "Paleta de Maquiagem 40 Cores", category="MLB1246")
    add(conn, "MLB4", "Perfume Masculino 100ml Batom", category="MLB1246")  # bloqueado
    score_and_route(conn, CFG, ["MLB1", "MLB2", "MLB3", "MLB4"], now=NOW)
    assert niches_of(conn, "MLB1") == ["casa", "noivas"]
    assert niches_of(conn, "MLB2") == ["casa"]
    assert niches_of(conn, "MLB3") == ["beleza", "noivas"]
    assert niches_of(conn, "MLB4") == ["beleza"]
    assert db.get_candidate(conn, "MLB1", "noivas").state is S.APPROVED


def test_destinations_split_telegram_and_whatsapp():
    from ofertinhas.publisher.publish import destination_groups

    conn = db.connect(":memory:")
    groups = {k: sorted(n.name for n in v) for k, v in destination_groups(conn, CFG).items()}
    assert groups == {(-100, None): ["beleza", "casa"],
                      (None, "120363000000000001@g.us"): ["noivas"]}
    conn.close()


def test_preview_shows_what_would_enter_and_why_the_rest_stays_out(conn):
    add(conn, "MLB1", "Jogo de Panelas Inox 5 Peças")
    add(conn, "MLB2", "Lixeira Inox 30 Litros")
    add(conn, "MLB3", "Batom Matte Vermelho", category="MLB1246")
    add(conn, "MLB9", "Fone Bluetooth", category="MLB1000")  # fora das categorias
    add(conn, "MLB8", "Jogo de Cama Casal", now=NOW - timedelta(days=5))  # fora da janela
    report = niche_preview(conn, CFG.for_niche("noivas"), NOW, days=3)
    assert report["offers_seen"] == 4 and report["in_categories"] == 3
    assert report["matched"] == 2 and report["decisions"] == {"automática": 2}
    assert report["left_out_by_reason"] == {"nenhum termo do nicho no título": 1}
    assert [m["title"] for m in report["matched_sample"]] == [
        "Jogo de Panelas Inox 5 Peças", "Batom Matte Vermelho"]
    assert report["left_out_sample"] == [
        {"title": "Lixeira Inox 30 Litros", "reason": "nenhum termo do nicho no título"}]
