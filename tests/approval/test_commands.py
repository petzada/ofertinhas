from datetime import UTC, datetime
from pathlib import Path

import pytest

from ofertinhas import db
from ofertinhas.approval.commands import CommandContext, run_command
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer
from ofertinhas.pipeline import niche_configs

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
EXAMPLE = Path(__file__).parents[2] / "config.example.yaml"
S = CandidateState


@pytest.fixture
def ctx():
    conn = db.connect(":memory:")
    yield CommandContext(conn=conn, cfg=load_config(EXAMPLE), now=NOW, chat_id=777)
    conn.close()


def run(ctx, text):
    name, *args = text.split()
    return run_command(name, args, ctx)


def seed(conn, mlb_id, niche="casa", state=S.PENDING, score=70.0):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title=f"Produto {mlb_id}", price=100, commission_pct=10,
        category_path=("MLB1574",), permalink="https://x", collected_at=NOW,
    ), now=NOW)
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=state, score=score, breakdown={},
        ref_price=100, decided_at=NOW,
    ))


def test_chatid(ctx):
    assert "777" in run(ctx, "chatid")


def test_corte_sets_thresholds(ctx):
    reply = run(ctx, "corte casa 85 65")
    assert "85" in reply
    casa = niche_configs(ctx.conn, ctx.cfg)["casa"]
    assert (casa.auto_approve_at, casa.manual_review_at) == (85, 65)


@pytest.mark.parametrize("text", ["corte casa 60 70", "corte casa x 1", "corte pets 80 60",
                                  "corte casa 80"])
def test_corte_invalid_keeps_settings(ctx, text):
    reply = run(ctx, text)
    assert "⚠️" in reply
    assert db.niche_overrides(ctx.conn, "casa") == {}


def test_peso(ctx):
    run(ctx, "peso tech full 20")
    assert niche_configs(ctx.conn, ctx.cfg)["tech"].weights.full == 20


def test_peso_unknown_criterion(ctx):
    assert "⚠️" in run(ctx, "peso tech brilho 5")


def test_pausar_and_retomar_niche(ctx):
    run(ctx, "pausar casa")
    assert niche_configs(ctx.conn, ctx.cfg)["casa"].paused
    run(ctx, "retomar casa")
    assert not niche_configs(ctx.conn, ctx.cfg)["casa"].paused


def test_pausar_all_niches(ctx):
    run(ctx, "pausar")
    assert all(n.paused for n in niche_configs(ctx.conn, ctx.cfg).values())
    run(ctx, "retomar")
    assert not any(n.paused for n in niche_configs(ctx.conn, ctx.cfg).values())


def test_pausar_coleta(ctx):
    run(ctx, "pausar coleta")
    assert db.get_setting(ctx.conn, db.EXTENSION_PAUSED_KEY)["reason"] == "manual"
    run(ctx, "retomar coleta")
    assert db.get_setting(ctx.conn, db.EXTENSION_PAUSED_KEY) is None


def test_fila_lists_pending_by_score(ctx):
    seed(ctx.conn, "MLB1", score=61)
    seed(ctx.conn, "MLB2", score=79)
    seed(ctx.conn, "MLB3", state=S.APPROVED)
    reply = run(ctx, "fila casa")
    assert reply.index("MLB2") < reply.index("MLB1")
    assert "pendentes: 2" in reply.lower()
    assert "aprovadas: 1" in reply.lower()


def test_top(ctx):
    seed(ctx.conn, "MLB1", score=61)
    assert "MLB1" in run(ctx, "top casa")
    assert db.get_candidate(ctx.conn, "MLB1", "casa").state is S.APPROVED
    assert "nenhuma" in run(ctx, "top casa").lower()


def test_stats_counts_posts_today(ctx):
    db.record_post(ctx.conn, mlb_id="MLB1", niche="casa", channel="telegram", chat="-1",
                   status="sent", sent_at=NOW)
    db.record_post(ctx.conn, mlb_id="MLB1", niche="casa", channel="whatsapp", chat="g",
                   status="failed", sent_at=NOW)
    reply = run(ctx, "stats")
    assert "casa" in reply and "telegram: 1" in reply.lower()


def test_unknown_command_shows_help(ctx):
    assert "/corte" in run(ctx, "xyz")
