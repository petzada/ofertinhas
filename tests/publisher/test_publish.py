import dataclasses
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

    async def send_image(self, jid, media_url, caption):
        if self.fail:
            raise self.fail
        self.sent.append((jid, media_url, caption))
        return f"wa{len(self.sent)}"


class FakeCardHost:
    def __init__(self):
        self.uploaded = {}

    async def upload(self, key, png):
        self.uploaded[key] = png
        return f"https://pub-x.r2.dev/{key}"


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


async def run(conn, config, tg, wa=None, dry_run=False, now=NOW, notes=None, host=None,
              wa_test=None):
    return await publish_due(conn, config, telegram=tg, whatsapp=wa,
                             card_host=host or FakeCardHost(), admin_chat_id=ADMIN,
                             dry_run=dry_run, now=now, notify=notes or Notes(), sleep=no_sleep,
                             whatsapp_test_jid=wa_test)


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
    tg, wa, host = FakeTelegram(), FakeWhatsApp(), FakeCardHost()
    assert await run(conn, cfg(wa=True), tg, wa, host=host) == ["MLB1"]
    jid, media_url, caption = wa.sent[0]
    assert jid == JID and media_url == "https://pub-x.r2.dev/cards/MLB1-casa.png"
    assert host.uploaded["cards/MLB1-casa.png"] == b"\x89PNG card"
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


async def test_dry_run_whatsapp_goes_only_to_the_test_chat(conn, tmp_path):
    seed(conn, tmp_path)
    tg, wa = FakeTelegram(), FakeWhatsApp()
    posted = await run(conn, cfg(wa=True), tg, wa, dry_run=True, wa_test="5511900000000")
    assert posted == ["MLB1"]
    jid, _, caption = wa.sent[0]
    assert jid == "5511900000000" and wa.presence == ["5511900000000"]
    assert caption.startswith("🧪 *TESTE • casa*")
    assert db.last_post_at(conn, JID) is None  # o grupo real não conta o teste
    assert db.last_post_at(conn, "dry-run:5511900000000") == NOW


async def test_dry_run_test_chat_still_needs_whatsapp_enabled(conn, tmp_path):
    seed(conn, tmp_path)
    wa = FakeWhatsApp()
    await run(conn, cfg(wa=False), FakeTelegram(), wa, dry_run=True, wa_test="5511900000000")
    assert wa.sent == []


async def test_niches_sharing_a_group_share_queue_and_pace(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", niche="casa", score=80)
    seed(conn, tmp_path, "MLB2", niche="tech", score=95)
    seed(conn, tmp_path, "MLB3", niche="pets", score=50)  # grupo próprio
    tg = FakeTelegram()
    posted = await run(conn, cfg(), tg)
    assert sorted(posted) == ["MLB2", "MLB3"]  # o melhor do grupo compartilhado + o de pets
    assert await run(conn, cfg(), tg, now=NOW + timedelta(minutes=10)) == []
    assert await run(conn, cfg(), tg, now=NOW + timedelta(minutes=31)) == ["MLB1"]


async def test_automatic_offers_go_before_your_approvals(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", score=60)  # automática: passou na regra mais dura
    seed(conn, tmp_path, "MLB2", score=95, notified=True)  # aprovada por você: complemento
    tg = FakeTelegram()
    assert await run(conn, cfg(), tg) == ["MLB1"]
    assert await run(conn, cfg(), tg, now=NOW + timedelta(minutes=31)) == ["MLB2"]


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


async def test_force_posts_outside_the_window_and_interval(conn, tmp_path):
    three_am = datetime(2026, 10, 22, 6, tzinfo=UTC)  # 03:00 em São Paulo
    seed(conn, tmp_path, "MLB1", seen=three_am)
    seed(conn, tmp_path, "MLB2", seen=three_am)
    tg = FakeTelegram()
    assert await run(conn, cfg(), tg, now=three_am) == []
    posted = await publish_due(conn, cfg(), telegram=tg, card_host=FakeCardHost(),
                               admin_chat_id=ADMIN, dry_run=False, now=three_am,
                               notify=Notes(), sleep=no_sleep, force=True)
    assert len(posted) == 1 and tg.sent[0][0] == str(GROUP)
    assert db.posts_today(conn, str(GROUP), three_am) == 1  # conta no limite do dia


async def test_force_can_pick_one_offer(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", score=90)
    seed(conn, tmp_path, "MLB2", score=50)
    tg = FakeTelegram()
    posted = await publish_due(conn, cfg(), telegram=tg, card_host=FakeCardHost(),
                               admin_chat_id=ADMIN, dry_run=False, now=NOW, notify=Notes(),
                               sleep=no_sleep, force=True, only_mlb="MLB2")
    assert posted == ["MLB2"]
    assert db.get_candidate(conn, "MLB1", "casa").state is S.RENDERED


SPLIT = """
whatsapp_enabled: true
defaults:
  pacing: {{min_interval_min: 45, jitter_min: 0, window: ["06:00", "22:00"], max_posts_per_day: 32}}
  whatsapp_pacing: {{min_interval_min: 75, jitter_min: 0, window: ["08:00", "18:00"],
                    max_posts_per_day: 10}}
niches:
  casa:
    categories: [MLB1574]
    telegram_chat_id: {group}
    whatsapp_group_jid: "{jid}"
  pets:
    categories: [MLB1071]
    whatsapp_group_jid: "120363000000000002@g.us"
"""


def split_cfg():
    return load_config_text(SPLIT.format(group=GROUP, jid=JID))


def sp_time(hour, minute=0):
    return datetime(2026, 10, 22, hour + 3, minute, tzinfo=UTC)  # São Paulo = UTC-3


async def test_each_channel_has_its_own_window(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", seen=sp_time(6, 50), score=90)
    seed(conn, tmp_path, "MLB2", seen=sp_time(6, 50), score=80)
    tg, wa = FakeTelegram(), FakeWhatsApp()
    assert await run(conn, split_cfg(), tg, wa, now=sp_time(7)) == ["MLB1"]  # 7h: só Telegram
    assert wa.sent == []
    assert await run(conn, split_cfg(), tg, wa, now=sp_time(8)) == ["MLB2", "MLB1"]
    assert [j for j, _, _ in wa.sent] == [JID]  # 8h: o WhatsApp abre com a melhor do período
    assert wa.sent[0][2].startswith("🔥 *Air Fryer*")


async def test_whatsapp_gets_the_best_of_the_period_once(conn, tmp_path):
    for mlb, score in (("MLB1", 90), ("MLB2", 80), ("MLB3", 70)):
        seed(conn, tmp_path, mlb, seen=sp_time(8, 50), score=score)
    tg, wa = FakeTelegram(), FakeWhatsApp()
    await run(conn, split_cfg(), tg, wa, now=sp_time(9))  # TG e WA: MLB1
    await run(conn, split_cfg(), tg, wa, now=sp_time(9, 45))  # TG: MLB2; WA espera 75 min
    await run(conn, split_cfg(), tg, wa, now=sp_time(10, 15))  # WA: MLB2, que já foi ao TG
    assert [c for c, _, _ in tg.sent] == [str(GROUP)] * 2
    assert len(wa.sent) == 2
    sent_wa = [r[0] for r in conn.execute(
        "SELECT mlb_id FROM posts WHERE channel = 'whatsapp' ORDER BY sent_at")]
    assert sent_wa == ["MLB1", "MLB2"]
    assert db.get_candidate(conn, "MLB3", "casa").state is S.RENDERED  # fica para o Telegram


async def test_whatsapp_does_not_repeat_an_offer(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", seen=sp_time(8, 50))
    tg, wa = FakeTelegram(), FakeWhatsApp()
    await run(conn, split_cfg(), tg, wa, now=sp_time(9))
    assert await run(conn, split_cfg(), tg, wa, now=sp_time(10, 30)) == []
    assert len(wa.sent) == 1


async def test_whatsapp_only_group_takes_the_offer_out_of_the_queue(conn, tmp_path):
    seed(conn, tmp_path, "MLB9", niche="pets", seen=sp_time(8, 50))
    wa = FakeWhatsApp()
    assert await run(conn, split_cfg(), FakeTelegram(), wa, now=sp_time(9)) == ["MLB9"]
    assert wa.sent[0][0] == "120363000000000002@g.us"
    assert db.get_candidate(conn, "MLB9", "pets").state is S.POSTED


async def test_whatsapp_skips_an_offer_whose_card_is_missing(conn, tmp_path):
    seed(conn, tmp_path, "MLB1", seen=sp_time(8, 50), score=95)  # postada pelo PC antes da
    db.save_candidate(conn, dataclasses.replace(  # virada: o card ficou no disco de lá
        db.get_candidate(conn, "MLB1", "casa"), state=S.POSTED, decided_at=sp_time(7),
        card_path=str(tmp_path / "sumiu.png")))
    seed(conn, tmp_path, "MLB2", seen=sp_time(8, 50), score=80)
    db.record_post(conn, mlb_id="MLB2", niche="casa", channel="telegram", chat=str(GROUP),
                   status="sent", sent_at=sp_time(8, 50))  # Telegram ainda não está na vez
    wa = FakeWhatsApp()
    assert await run(conn, split_cfg(), FakeTelegram(), wa, now=sp_time(9)) == ["MLB2"]
    assert len(wa.sent) == 1


async def test_telegram_sends_an_offer_back_to_render_when_its_card_is_missing(conn, tmp_path):
    seed(conn, tmp_path, "MLB1")
    (tmp_path / "MLB1.png").unlink()
    tg = FakeTelegram()
    assert await run(conn, cfg(), tg) == []
    cand = db.get_candidate(conn, "MLB1", "casa")
    assert cand.state is S.LINKED and cand.card_path is None and tg.sent == []
