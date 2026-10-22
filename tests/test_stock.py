from datetime import datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.config import load_config_text
from ofertinhas.models import TZ, Candidate, CandidateState, Offer
from ofertinhas.stock import alert_low_stock, group_stock, post_slots

S = CandidateState
GROUP = -1004330132499
CONFIG = f"""
defaults:
  max_offer_age_hours: 6
  pacing:
    min_interval_min: 25
    jitter_min: 0
    window: ["08:00", "23:00"]
    max_posts_per_day: 25
niches:
  casa:
    categories: [MLB1574]
    telegram_chat_id: {GROUP}
"""


def sp(hour, minute=0):
    return datetime(2026, 10, 22, hour, minute, tzinfo=TZ)


@pytest.fixture
def cfg():
    return load_config_text(CONFIG)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def stock(conn, n, seen, state=S.RENDERED, start=0):
    for i in range(start, start + n):
        mlb = f"MLB{i}"
        db.upsert_offer(conn, Offer(mlb_id=mlb, title="x", price=10, commission_pct=25,
                                    category_path=("MLB1574",), permalink="https://x",
                                    collected_at=seen), now=seen)
        db.save_candidate(conn, Candidate(mlb_id=mlb, niche="casa", state=state, score=90 - i,
                                          breakdown={}, ref_price=10, decided_at=seen))


class Notes:
    def __init__(self):
        self.sent: list[str] = []

    async def __call__(self, text):
        self.sent.append(text)


def test_slots_follow_window_interval_and_daily_cap(cfg):
    slots = post_slots(sp(7), None, 0, cfg.for_niche("casa").pacing)
    assert slots[0] == sp(8) and slots[1] == sp(8, 25)
    assert len(slots) == 25 and slots[-1] == sp(18)  # 8h + 24 × 25 min
    assert post_slots(sp(23, 30), None, 0, cfg.for_niche("casa").pacing) == []
    assert len(post_slots(sp(9), sp(8, 50), 20, cfg.for_niche("casa").pacing)) == 5


def test_stock_ends_when_the_offers_run_out(conn, cfg):
    stock(conn, 3, seen=sp(7, 30))
    [g] = group_stock(conn, cfg, sp(7), dry_run=False)
    assert (g.ready, g.waiting_links) == (3, 0)
    assert g.ends_at == sp(9, 15)  # 8:00, 8:25 e 8:50 usam as três


def test_stock_ends_when_the_offers_expire(conn, cfg):
    stock(conn, 20, seen=sp(4, 30))  # valem até 10:30
    [g] = group_stock(conn, cfg, sp(7), dry_run=False)
    assert g.ends_at == sp(10, 55)  # 7 posts até 10:30, depois todas venceram


def test_offers_waiting_for_a_link_extend_the_stock_only_if_linked(conn, cfg):
    stock(conn, 1, seen=sp(7, 30))
    stock(conn, 4, seen=sp(7, 30), state=S.APPROVED, start=10)
    [g] = group_stock(conn, cfg, sp(7), dry_run=False)
    assert (g.ready, g.waiting_links) == (1, 4)
    assert g.ends_at == sp(8, 25) and g.ends_at_with_links == sp(10, 5)


def test_stock_that_covers_the_rest_of_the_day_has_no_end(conn, cfg):
    stock(conn, 30, seen=sp(17))  # valem até 23:00, o fim da janela
    [g] = group_stock(conn, cfg, sp(17), dry_run=False)
    assert g.ends_at is None and g.as_dict()["ends_at"] is None


def test_dry_run_counts_its_own_pace(conn, cfg):
    db.record_post(conn, mlb_id="MLB9", niche="casa", channel="telegram", chat=str(GROUP),
                   status="sent", sent_at=sp(8))
    [real] = group_stock(conn, cfg, sp(8, 5), dry_run=False)
    [test] = group_stock(conn, cfg, sp(8, 5), dry_run=True)
    assert (real.posts_today, test.posts_today) == (1, 0)


async def test_alert_an_hour_before_and_then_every_two_hours(conn, cfg):
    notes = Notes()
    assert await alert_low_stock(conn, cfg, notes, sp(6, 30), dry_run=False) == 0  # 8h longe
    assert await alert_low_stock(conn, cfg, notes, sp(7), dry_run=False) == 1
    assert "acaba às 08:00" in notes.sent[0] and "Coletar agora" in notes.sent[0]
    assert await alert_low_stock(conn, cfg, notes, sp(7, 5), dry_run=False) == 0
    assert await alert_low_stock(conn, cfg, notes, sp(9, 1), dry_run=False) == 1
    assert "já está sem ofertas" in notes.sent[1]


async def test_no_alert_with_enough_stock_or_at_night(conn, cfg):
    notes = Notes()
    stock(conn, 15, seen=sp(7, 30))
    assert await alert_low_stock(conn, cfg, notes, sp(8), dry_run=False) == 0
    assert await alert_low_stock(conn, cfg, Notes(), sp(23, 30) + timedelta(minutes=1),
                                 dry_run=False) == 0
