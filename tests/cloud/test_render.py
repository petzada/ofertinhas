from datetime import UTC, datetime
from pathlib import Path

import pytest

from ofertinhas import db
from ofertinhas.cloud.draw import draw_cards, offer_from_json, offer_to_json
from ofertinhas.cloud.render import apply_rendered, render_tasks
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
S = CandidateState


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def offer(mlb_id="MLB1"):
    return Offer(mlb_id=mlb_id, title="Jogo de Panelas Genebra 5 Peças", price=199.9,
                 original_price=349.9, commission_pct=22, category_path=("MLB1574",),
                 permalink="https://x", affiliate_link="https://meli.la/abc", pix_only=True,
                 collected_at=NOW, shipping_checked_at=NOW)


def seed(conn, n=4, state=S.LINKED):
    for i in range(n):
        db.upsert_offer(conn, offer(f"MLB{i}"), now=NOW)
        db.set_affiliate_link(conn, f"MLB{i}", "https://meli.la/abc")  # o upsert não grava
        db.save_candidate(conn, Candidate(mlb_id=f"MLB{i}", niche="casa", state=state,
                                          score=90 - i, breakdown={}, ref_price=199.9,
                                          decided_at=NOW))


def test_offer_survives_the_trip_to_the_worker():
    original = offer()
    original.last_seen_at = NOW
    assert offer_from_json(offer_to_json(original)) == original


def test_tasks_bring_the_best_linked_with_caption_and_brand(conn):
    seed(conn)
    cfg = load_config(ROOT / "config.example.yaml")
    tasks = render_tasks(conn, cfg, ROOT / "templates" / "text", NOW, limit=3)
    assert [t["mlb_id"] for t in tasks] == ["MLB0", "MLB1", "MLB2"]
    assert tasks[0]["brand"] == cfg.brand and "meli.la/abc" in tasks[0]["caption"]


async def test_worker_draws_saves_and_the_do_marks_rendered(conn):
    seed(conn, n=2)
    cfg = load_config(ROOT / "config.example.yaml")
    tasks = render_tasks(conn, cfg, ROOT / "templates" / "text", NOW)
    saved = {}

    async def save(name, png):
        saved[name] = png
        return f"cards/{name}"

    async def no_photo(url):
        return None

    tasks[1]["offer"]["price"] = "quebrado"  # uma tarefa ruim não trava a outra
    results = await draw_cards(tasks, no_photo, save)
    assert [r["card_path"] for r in results] == ["cards/MLB0-casa.png"]
    assert saved["MLB0-casa.png"].startswith(b"\x89PNG")
    assert apply_rendered(conn, results) == 1
    cand = db.get_candidate(conn, "MLB0", "casa")
    assert cand.state is S.RENDERED and cand.card_path == "cards/MLB0-casa.png"
    assert apply_rendered(conn, results) == 0  # já não está mais como linked
