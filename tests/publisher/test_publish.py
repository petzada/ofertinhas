from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.config import load_config_text
from ofertinhas.models import Candidate, CandidateState, Offer
from ofertinhas.publisher.publish import publish_due
from ofertinhas.publisher.telegram import TelegramError
from ofertinhas.publisher.whatsapp import WhatsAppError

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)  # 12:00 em São Paulo
ADMIN = 777
GROUP = -1004330132499
JID = "120363000000000001@g.us"
S = CandidateState

CONFIG = """
whatsapp_enabled: {wa}
niches:
  casa:
    categories: [MLB1574]
    telegram_chat_id: {group}
    whatsapp_group_jid: "{jid}"
  tech:
    categories: [MLB1648]
    telegram_chat_id: {group}
    whatsapp_group_jid: "{jid}"
  pets:
    categories: [MLB1071]
    telegram_chat_id: -1009999
"""


def cfg(wa=False):
    return load_config_text(CONFIG.format(wa=str(wa).lower(), group=GROUP, jid=JID))


class FakeTelegram:
    def __init__(self, fail=None):
        self.sent = []
        self.fail = fail

    async def send_photo(self, chat_id, png, caption_html):
        if self.fail:
            raise self.fail
        self.sent.append((str(chat_id), png, caption_html))
        return str(len(self.sent))


class FakeWhatsApp:
    def __init__(self, fail=None):
        self.sent = []
        self.presence = []
        self.fail = fail

    async def send_presence(self, jid):
        self.presence.append(jid)

    async def send_image(self, jid, png, caption):
        if self.fail:
            raise self.fail
        self.sent.append((jid, png, caption))
        return f"wa{len(self.sent)}"


class Notes:
    def __init__(self):
        self.sent = []

    async def __call__(self, text):
        self.sent.append(text)


async def no_sleep(_seconds):
    pass


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def seed(conn, tmp_path, mlb_id="MLB1", niche="casa", score=90.0, seen=NOW, state=S.RENDERED,
         notified=False):
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
        card_path=str(card), notified_at=seen if notified else None,
    ))


async def run(conn, config, tg, wa=None, dry_run=False, now=NOW, notes=None):
    return await publish_due(conn, config, telegram=tg, whatsapp=wa, admin_chat_id=ADMIN,
                             dry_run=dry_run, now=now, notify=notes or Notes(), sleep=no_sleep)


async def test_real_mode_posts_to_telegram_group(conn, tmp_path):
    seed(conn, tmp_path)
    tg = FakeTelegram()
    assert await run(conn, cfg(), tg) == ["MLB1"]
    chat, png, caption = tg.sent[0]
    assert chat == str(GROUP) and png == b"\x89PNG card"
    assert "<b>Air Fryer</b>" in caption and "<s>R$ 499</s>" in caption
    assert not caption.startswith("🧪")
    cand = db.get_candidate(conn, "MLB1", "casa")
    assert cand.state is S.POSTED and cand.decided_at == NOW


async def test_whatsapp_follows_telegram_when_enabled(conn, tmp_path):
    seed(conn, tmp_path)
    tg, wa = FakeTelegram(), FakeWhatsApp()
    assert await run(conn, cfg(wa=True), tg, wa) == ["MLB1"]
    jid, png, caption = wa.sent[0]
    assert jid == JID and png == b"\x89PNG card"
    assert "*Air Fryer*" in caption and "~R$ 499~" in caption  # formato do WhatsApp
    assert wa.presence == [JID]
    channels = {r[0] for r in conn.execute("SELECT channel FROM posts WHERE status = 'sent'")}
    assert channels == {"telegram", "whatsapp"}


async def test_whatsapp_locked_sends_nothing(conn, tmp_path):
    seed(conn, tmp_path)
    wa = FakeWhatsApp()
    await run(conn, cfg(wa=False), FakeTelegram(), wa)
    assert wa.sent == []


async def test_dry_run_goes_to_admin_and_never_to_whatsapp(conn, tmp_path):
    seed(conn, tmp_path)
    tg, wa = FakeTelegram(), FakeWhatsApp()
    assert await run(conn, cfg(wa=True), tg, wa, dry_run=True) == ["MLB1"]
    chat, _, caption = tg.sent[0]
    assert chat == str(ADMIN) and caption.startswith("🧪 <b>TESTE • casa</b>")
    assert wa.sent == []
    assert db.last_post_at(conn, str(GROUP)) is None  # teste não conta no ritmo real


async def test_niches_sharing_a_group_share_queue_and_pace(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", niche="casa", score=80)
    seed(conn, tmp_path, "MLB2", niche="tech", score=95)
    seed(conn, tmp_path, "MLB3", niche="pets", score=50)  # grupo próprio
    tg = FakeTelegram()
    posted = await run(conn, cfg(), tg)
    assert sorted(posted) == ["MLB2", "MLB3"]  # o melhor do grupo compartilhado + o de pets
    assert await run(conn, cfg(), tg, now=NOW + timedelta(minutes=10)) == []
    assert await run(conn, cfg(), tg, now=NOW + timedelta(minutes=31)) == ["MLB1"]


async def test_your_approvals_go_first_in_the_group(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", score=95)
    seed(conn, tmp_path, "MLB2", score=60, notified=True)  # aprovada por você
    assert await run(conn, cfg(), FakeTelegram()) == ["MLB2"]


async def test_paused_niche_is_skipped(conn, tmp_path):
    seed(conn, tmp_path)
    db.set_niche_override(conn, "casa", "paused", True)
    assert await run(conn, cfg(), FakeTelegram()) == []


async def test_stale_offer_expires_instead_of_posting(conn, tmp_path):
    seed(conn, tmp_path, seen=NOW - timedelta(hours=7))
    tg = FakeTelegram()
    assert await run(conn, cfg(), tg) == []
    assert db.get_candidate(conn, "MLB1", "casa").state is S.EXPIRED


async def test_telegram_failure_backs_off_and_warns(conn, tmp_path):
    seed(conn, tmp_path)
    notes = Notes()
    tg = FakeTelegram(fail=TelegramError("Bad Request: chat not found", retryable=False))
    assert await run(conn, cfg(), tg, notes=notes) == []
    assert db.get_candidate(conn, "MLB1", "casa").state is S.RENDERED
    assert any("chat not found" in n for n in notes.sent)
    tg.fail = None
    assert await run(conn, cfg(), tg, now=NOW + timedelta(minutes=5)) == []
    assert await run(conn, cfg(), tg, now=NOW + timedelta(minutes=11)) == ["MLB1"]


async def test_whatsapp_failure_does_not_undo_telegram(conn, tmp_path):
    seed(conn, tmp_path)
    notes = Notes()
    wa = FakeWhatsApp(fail=WhatsAppError("instância desconectada", retryable=False))
    assert await run(conn, cfg(wa=True), FakeTelegram(), wa, notes=notes) == ["MLB1"]
    assert db.get_candidate(conn, "MLB1", "casa").state is S.POSTED
    assert any("WhatsApp" in n for n in notes.sent)


async def test_dry_run_ignores_posting_window_but_real_mode_does_not(conn, tmp_path):
    three_am = datetime(2026, 10, 22, 6, tzinfo=UTC)  # 03:00 em São Paulo
    seed(conn, tmp_path, seen=three_am)
    tg = FakeTelegram()
    assert await run(conn, cfg(), tg, now=three_am) == []
    assert await run(conn, cfg(), tg, dry_run=True, now=three_am) == ["MLB1"]


async def test_nothing_ready_nothing_sent(conn, tmp_path):
    seed(conn, tmp_path, state=S.LINKED)
    tg = FakeTelegram()
    assert await run(conn, cfg(), tg) == []
    assert tg.sent == []
