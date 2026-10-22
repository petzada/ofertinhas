from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ofertinhas import db
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer
from ofertinhas.publisher.publish import publish_due
from ofertinhas.publisher.telegram import TelegramError

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)  # 12:00 em São Paulo
EXAMPLE = Path(__file__).parents[2] / "config.example.yaml"
ADMIN = 777
S = CandidateState


class FakeTelegram:
    def __init__(self, fail=None):
        self.sent = []
        self.fail = fail

    async def send_photo(self, chat_id, png, caption_html):
        if self.fail:
            raise self.fail
        self.sent.append((str(chat_id), png, caption_html))
        return str(len(self.sent))


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def cfg():
    return load_config(EXAMPLE)


def seed(conn, tmp_path, mlb_id="MLB1", niche="casa", score=90.0, seen=NOW, state=S.RENDERED):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title="Air Fryer", price=299.9, commission_pct=12,
        category_path=("MLB1574",), permalink="https://x", collected_at=seen,
        affiliate_link="https://meli.la/abc",
    ), now=seen)
    card = tmp_path / f"{mlb_id}.png"
    card.write_bytes(b"\x89PNG card")
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=state, score=score, breakdown={}, ref_price=299.9,
        decided_at=seen, caption="🔥 *Air Fryer* por ~R$ 499~\n👉 https://meli.la/abc",
        card_path=str(card),
    ))


class Notes:
    def __init__(self):
        self.sent = []

    async def __call__(self, text):
        self.sent.append(text)


async def run(conn, cfg, telegram, dry_run=True, now=NOW, notify=None):
    return await publish_due(conn, cfg, telegram=telegram, admin_chat_id=ADMIN,
                             dry_run=dry_run, now=now, notify=notify or Notes())


async def test_dry_run_posts_to_admin_with_test_label(conn, cfg, tmp_path):
    seed(conn, tmp_path)
    tg = FakeTelegram()
    assert await run(conn, cfg, tg) == ["MLB1"]
    chat, png, caption = tg.sent[0]
    assert chat == str(ADMIN) and png == b"\x89PNG card"
    assert caption.startswith("🧪 <b>TESTE • casa</b>")
    assert "<b>Air Fryer</b>" in caption and "<s>R$ 499</s>" in caption
    cand = db.get_candidate(conn, "MLB1", "casa")
    assert cand.state is S.POSTED and cand.decided_at == NOW
    assert db.last_post_at(conn, "dry-run:casa") == NOW
    assert db.last_post_at(conn, str(ADMIN)) is None  # teste não conta como post real


async def test_real_mode_posts_to_the_niche_group(conn, cfg, tmp_path):
    seed(conn, tmp_path)
    tg = FakeTelegram()
    await run(conn, cfg, tg, dry_run=False)
    chat, _, caption = tg.sent[0]
    assert chat == "-1001234567890"
    assert not caption.startswith("🧪")
    assert db.last_post_at(conn, "-1001234567890") == NOW


async def test_best_offer_first_and_pacing_between_posts(conn, cfg, tmp_path):
    seed(conn, tmp_path, "MLB1", score=80)
    seed(conn, tmp_path, "MLB2", score=95)
    tg = FakeTelegram()
    assert await run(conn, cfg, tg) == ["MLB2"]
    assert await run(conn, cfg, tg, now=NOW + timedelta(minutes=10)) == []
    assert await run(conn, cfg, tg, now=NOW + timedelta(minutes=31)) == ["MLB1"]


async def test_paused_niche_is_skipped(conn, cfg, tmp_path):
    seed(conn, tmp_path)
    db.set_niche_override(conn, "casa", "paused", True)
    assert await run(conn, cfg, FakeTelegram()) == []


async def test_stale_offer_expires_instead_of_posting(conn, cfg, tmp_path):
    seed(conn, tmp_path, seen=NOW - timedelta(hours=7))
    tg = FakeTelegram()
    assert await run(conn, cfg, tg) == []
    assert tg.sent == []
    assert db.get_candidate(conn, "MLB1", "casa").state is S.EXPIRED


async def test_telegram_failure_keeps_offer_backs_off_and_warns(conn, cfg, tmp_path):
    seed(conn, tmp_path)
    notes = Notes()
    tg = FakeTelegram(fail=TelegramError("Bad Request: chat not found", retryable=False))
    assert await run(conn, cfg, tg, dry_run=False, notify=notes) == []
    assert db.get_candidate(conn, "MLB1", "casa").state is S.RENDERED
    assert any("chat not found" in n for n in notes.sent)
    tg.fail = None
    assert await run(conn, cfg, tg, dry_run=False, now=NOW + timedelta(minutes=5)) == []
    assert await run(conn, cfg, tg, dry_run=False, now=NOW + timedelta(minutes=11)) == ["MLB1"]


async def test_dry_run_ignores_posting_window_but_real_mode_does_not(conn, cfg, tmp_path):
    three_am = datetime(2026, 10, 22, 6, tzinfo=UTC)  # 03:00 em São Paulo
    seed(conn, tmp_path, seen=three_am)
    tg = FakeTelegram()
    assert await run(conn, cfg, tg, dry_run=False, now=three_am) == []
    assert await run(conn, cfg, tg, dry_run=True, now=three_am) == ["MLB1"]


async def test_nothing_ready_nothing_sent(conn, cfg, tmp_path):
    seed(conn, tmp_path, state=S.LINKED)
    tg = FakeTelegram()
    assert await run(conn, cfg, tg) == []
    assert tg.sent == []
