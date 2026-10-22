from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from ofertinhas import db
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer
from ofertinhas.pipeline import render_linked

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
EXAMPLE = Path(__file__).parents[1] / "config.example.yaml"
LINK = "https://mercadolivre.com/sec/1AbC2dE"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def templates(tmp_path):
    d = tmp_path / "templates"
    d.mkdir()
    (d / "casa.txt").write_text("CASA {titulo_curto}\n👉 {link}", encoding="utf-8")
    (d / "default.txt").write_text("DEF {link}", encoding="utf-8")
    return d


def seed(conn, mlb_id="MLB1", niche="casa", state=CandidateState.LINKED, link=LINK):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title="Air Fryer", price=299.9, original_price=499.9,
        commission_pct=12, category_path=("MLB1574",), permalink="https://x",
        image_url="https://img/x.png", collected_at=NOW,
    ), now=NOW)
    if link:
        db.set_affiliate_link(conn, mlb_id, link)
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=state, score=90, breakdown={},
        ref_price=299.9, decided_at=NOW,
    ))


async def fake_image(url):
    return Image.new("RGB", (100, 100), "blue")


async def no_image(url):
    return None


async def test_linked_becomes_rendered_with_caption_and_card(conn, templates, tmp_path):
    seed(conn)
    count = await render_linked(
        conn, load_config(EXAMPLE), tmp_path / "cards", templates, fake_image, now=NOW
    )
    cand = db.get_candidate(conn, "MLB1", "casa")
    assert count == 1
    assert cand.state is CandidateState.RENDERED
    assert cand.caption == f"CASA Air Fryer\n👉 {LINK}"
    assert Path(cand.card_path).read_bytes().startswith(b"\x89PNG")


async def test_other_states_are_untouched(conn, templates, tmp_path):
    seed(conn, state=CandidateState.APPROVED, link=None)
    count = await render_linked(
        conn, load_config(EXAMPLE), tmp_path / "cards", templates, fake_image, now=NOW
    )
    assert count == 0
    assert db.get_candidate(conn, "MLB1", "casa").state is CandidateState.APPROVED


async def test_renders_even_without_product_photo(conn, templates, tmp_path):
    seed(conn)
    await render_linked(conn, load_config(EXAMPLE), tmp_path / "cards", templates, no_image,
                        now=NOW)
    assert db.get_candidate(conn, "MLB1", "casa").state is CandidateState.RENDERED


async def test_one_broken_candidate_does_not_block_others(conn, templates, tmp_path):
    seed(conn, "MLB1")
    seed(conn, "MLB2")
    with conn:  # simula inconsistência: link apagado depois de linked
        conn.execute("UPDATE offers SET affiliate_link = NULL WHERE mlb_id = 'MLB1'")
    count = await render_linked(
        conn, load_config(EXAMPLE), tmp_path / "cards", templates, fake_image, now=NOW
    )
    assert count == 1
    assert db.get_candidate(conn, "MLB2", "casa").state is CandidateState.RENDERED
    assert db.get_candidate(conn, "MLB1", "casa").state is CandidateState.LINKED


async def test_unknown_niche_uses_default_template(conn, templates, tmp_path):
    seed(conn, niche="pets")
    await render_linked(conn, load_config(EXAMPLE), tmp_path / "cards", templates, fake_image,
                        now=NOW)
    assert db.get_candidate(conn, "MLB1", "pets").caption == f"DEF {LINK}"
