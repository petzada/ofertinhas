"""Enquete semanal no grupo de WhatsApp e votos que chegam pelo webhook da WhatsMiau."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.config import ConfigError, load_config_text
from ofertinhas.polls import BANK, Poll, next_poll, record_vote, results, send_weekly_polls

JID = "120363000000000001@g.us"
THURSDAY_1930 = datetime(2026, 10, 22, 22, 30, tzinfo=UTC)  # quinta, 19:30 em São Paulo
CFG = load_config_text(f"""
whatsapp_enabled: true
niches:
  noivas:
    categories: [MLB1574]
    whatsapp_group_jid: "{JID}"
    polls: {{weekday: qui, at: "19:30"}}
  casa:
    categories: [MLB1574]
    telegram_chat_id: -100
""")


class FakeWhatsApp:
    def __init__(self):
        self.polls = []

    async def send_poll(self, jid, question, options, multi):
        self.polls.append((jid, question, options, multi))
        return f"MSG{len(self.polls)}"


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def notes():
    return []


async def send(conn, wa, notes, now, cfg=CFG, **kw):
    async def notify(text):
        notes.append(text)

    kw.setdefault("dry_run", False)
    return await send_weekly_polls(conn, cfg, wa, now, notify, **kw)


def test_rotation_goes_through_the_bank_then_repeats_the_oldest():
    bank = (Poll("a", "A?", ("1", "2")), Poll("b", "B?", ("1", "2")), Poll("c", "C?", ("1", "2")))
    assert next_poll(bank, []).key == "a"
    assert next_poll(bank, ["a"]).key == "b"
    assert next_poll(bank, ["a", "b", "c"]).key == "a"
    assert next_poll(bank, ["a", "b", "c", "a"]).key == "b"


def test_bank_respects_whatsapp_limits():
    for poll in BANK["noivas"]:
        assert 2 <= len(poll.options) <= 12, poll.key
        assert len(set(poll.options)) == len(poll.options), poll.key
    assert len({p.key for p in BANK["noivas"]}) == len(BANK["noivas"])


def test_polls_need_a_whatsapp_group_and_quoted_time():
    with pytest.raises(ConfigError, match="polls precisa de whatsapp_group_jid"):
        load_config_text("""
niches:
  casa: {categories: [MLB1574], telegram_chat_id: -100, polls: {weekday: qui, at: "19:30"}}
""")
    with pytest.raises(ConfigError, match="aspas"):
        load_config_text(f"""
niches:
  noivas: {{categories: [MLB1574], whatsapp_group_jid: "{JID}", polls: {{weekday: qui, at: 19:30}}}}
""")


async def test_sends_once_on_the_day_and_time(conn, notes):
    wa = FakeWhatsApp()
    assert await send(conn, wa, notes, THURSDAY_1930 - timedelta(minutes=5)) == []
    assert await send(conn, wa, notes, THURSDAY_1930) == ["noivas:data"]
    assert await send(conn, wa, notes, THURSDAY_1930 + timedelta(minutes=5)) == []
    jid, question, options, multi = wa.polls[0]
    assert jid == JID and question.endswith("Quando é o grande dia?") and not multi
    assert "Já casei 🥂" in options


async def test_late_window_and_other_days(conn, notes):
    wa = FakeWhatsApp()
    assert await send(conn, wa, notes, THURSDAY_1930 + timedelta(hours=2, minutes=5)) == []
    assert await send(conn, wa, notes, THURSDAY_1930 - timedelta(days=1)) == []
    assert await send(conn, wa, notes, THURSDAY_1930 + timedelta(hours=1)) == ["noivas:data"]
    next_week = THURSDAY_1930 + timedelta(days=7)
    assert await send(conn, wa, notes, next_week) == ["noivas:achados"]
    assert wa.polls[1][3] is True  # múltipla escolha


async def test_dry_run_goes_only_to_the_test_chat(conn, notes):
    wa = FakeWhatsApp()
    assert await send(conn, wa, notes, THURSDAY_1930, dry_run=True) == []  # sem destino
    test_jid = "5511999@s.whatsapp.net"
    sent = await send(conn, wa, notes, THURSDAY_1930, dry_run=True, test_jid=test_jid)
    assert sent == ["noivas:data"] and wa.polls[0][0] == test_jid


async def test_locked_whatsapp_sends_nothing(conn, notes):
    cfg = CFG.model_copy(update={"whatsapp_enabled": False})
    assert await send(conn, FakeWhatsApp(), notes, THURSDAY_1930, cfg=cfg) == []
    assert await send(conn, None, notes, THURSDAY_1930) == []


async def test_force_sends_now_and_reports_the_previous_result(conn, notes):
    wa = FakeWhatsApp()
    await send(conn, wa, notes, THURSDAY_1930)
    record_vote(conn, vote("MSG1", "5511911111111@s.whatsapp.net", ["2028 ou depois"]),
                THURSDAY_1930)
    monday = THURSDAY_1930 - timedelta(days=3)
    sent = await send(conn, wa, notes, monday, force_niche="noivas")
    assert sent == ["noivas:achados"]
    assert "Quando é o grande dia?" in notes[0] and "• 2028 ou depois: 1 (100%)" in notes[0]


def vote(poll_id, voter, selected):
    return {"event": "messages.upsert", "instance": "Ofertas01", "data": {
        "key": {"remoteJid": JID, "fromMe": False, "id": "VOTE1", "participant": voter},
        "messageType": "pollUpdateMessage",
        "message": {"pollUpdateMessage": {
            "pollCreationMessageKey": {"remoteJid": JID, "fromMe": True, "id": poll_id},
            "vote": {"selectedOptions": selected}}}}}


@pytest.fixture
async def poll(conn, notes):
    await send(conn, FakeWhatsApp(), notes, THURSDAY_1930)
    return db.get_poll(conn, "MSG1")


def sha(option):
    return hashlib.sha256(option.encode()).digest()


async def test_vote_by_name_hex_or_base64_hash(conn, poll):
    a, b, c = poll["options"][:3]
    assert record_vote(conn, vote("MSG1", "551191@s.whatsapp.net", [a]), THURSDAY_1930) == "voto"
    assert record_vote(conn, vote("MSG1", "551192@s.whatsapp.net", [sha(b).hex()]),
                       THURSDAY_1930) == "voto"
    assert record_vote(conn, vote("MSG1", "551193@s.whatsapp.net",
                                  [base64.b64encode(sha(c)).decode()]), THURSDAY_1930) == "voto"
    counts = results(conn, poll)["counts"]
    assert (counts[a], counts[b], counts[c]) == (1, 1, 1)


async def test_changed_or_removed_vote_counts_once(conn, poll):
    a, b = poll["options"][:2]
    voter = "551191@s.whatsapp.net"
    record_vote(conn, vote("MSG1", voter, [a]), THURSDAY_1930)
    record_vote(conn, vote("MSG1", voter, [b]), THURSDAY_1930)
    result = results(conn, poll)
    assert result["voters"] == 1 and result["counts"][a] == 0 and result["counts"][b] == 1
    record_vote(conn, vote("MSG1", voter, []), THURSDAY_1930)
    assert results(conn, poll)["voters"] == 0


async def test_voter_is_stored_only_as_a_hash(conn, poll):
    record_vote(conn, vote("MSG1", "5511911111111@s.whatsapp.net", [poll["options"][0]]),
                THURSDAY_1930)
    voters = [r["voter"] for r in conn.execute("SELECT voter FROM poll_votes")]
    assert voters and "5511911111111" not in voters[0]


async def test_evolution_aggregate_format(conn, poll):
    a, b = poll["options"][:2]
    event = {"event": "messages.update", "data": {
        "key": {"id": "MSG1", "remoteJid": JID},
        "pollUpdates": [{"name": a, "voters": ["1@s.whatsapp.net", "2@s.whatsapp.net"]},
                        {"name": b, "voters": ["3@s.whatsapp.net"]}]}}
    assert record_vote(conn, event, THURSDAY_1930) == "voto"
    result = results(conn, poll)
    assert result["voters"] == 3 and result["counts"][a] == 2


async def test_unknown_option_is_kept_for_inspection(conn, poll):
    event = vote("MSG1", "551191@s.whatsapp.net", ["opção que não existe"])
    assert record_vote(conn, event, THURSDAY_1930) == "não entendi"
    kept = db.get_setting(conn, "wa:unparsed")
    assert len(kept) == 1 and "pollCreationMessageKey" in kept[0]["event"]


async def test_other_events_are_ignored(conn, poll):
    text = {"event": "messages.upsert", "data": {"key": {"id": "X"},
                                                 "message": {"conversation": "oi"}}}
    assert record_vote(conn, text, THURSDAY_1930) == "ignorado"
    assert record_vote(conn, vote("OUTRA", "1@s.whatsapp.net", ["x"]), THURSDAY_1930) \
        == "ignorado"
    assert record_vote(conn, {"event": "connection.update"}, THURSDAY_1930) == "ignorado"
    assert db.get_setting(conn, "wa:unparsed") is None


def whatsmiau_vote(poll_id, selected=None, poll_updates=None):
    """Formato real da WhatsMiau (22/10/2026); `selected`/`poll_updates` só vêm quando ela
    consegue pôr o nome da opção."""
    vote = {"encIv": "HxoffuFUnDhka41/", "encPayload": "tr6ZPIKll7+Dt6gRYCUT"}
    if selected is not None:
        vote["selectedOptions"] = selected
    data = {"contextInfo": {}, "instanceId": "ofertinhas_x",
            "key": {"addressingMode": "jid", "id": "3AED20129274EB6035BB",
                    "participant": "5511900000000@s.whatsapp.net", "remoteJid": JID},
            "message": {"pollUpdateMessage": {
                "pollCreationMessageKey": {"id": poll_id, "participant": "721@lid",
                                           "remoteJid": JID},
                "senderTimestampMs": "1792692500256", "vote": vote}},
            "messageType": "pollUpdateMessage", "pushName": "Marcio", "status": "received"}
    if poll_updates is not None:
        data["pollUpdates"] = poll_updates
    return {"instance": "ofertinhas_x", "event": "messages.upsert", "data": data}


async def test_encrypted_vote_counts_as_unreadable(conn, poll, notes):
    assert record_vote(conn, whatsmiau_vote("MSG1"), THURSDAY_1930) == "voto"
    result = results(conn, poll)
    assert result["voters"] == 1 and result["unreadable"] == 1
    assert sum(result["counts"].values()) == 0
    assert db.get_setting(conn, "wa:unparsed") is None
    await send(conn, FakeWhatsApp(), notes, THURSDAY_1930 + timedelta(days=7))
    assert "1 voto(s) chegaram cifrados" in notes[-1]


async def test_whatsmiau_decrypted_vote_uses_the_poll_key_not_the_vote_id(conn, poll):
    a = poll["options"][1]
    event = whatsmiau_vote("MSG1", selected=[a],
                           poll_updates=[{"name": a, "voters": ["5511900000000@s.whatsapp.net"]}])
    assert record_vote(conn, event, THURSDAY_1930) == "voto"
    result = results(conn, poll)
    assert result["counts"][a] == 1 and result["unreadable"] == 0
