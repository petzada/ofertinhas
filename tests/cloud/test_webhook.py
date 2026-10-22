from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ofertinhas import db
from ofertinhas.approval.actions import custom_caption
from ofertinhas.approval.bot import BotDeps
from ofertinhas.cloud.webhook import AWAITING_EDIT_KEY, handle_update
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
EXAMPLE = Path(__file__).parents[2] / "config.example.yaml"
ADMIN = 777
S = CandidateState


class FakeBot:
    """Só o que os atalhos da PTB (answer, reply_text, edit_*) chamam."""

    defaults = None

    def __init__(self):
        self.answer_callback_query = AsyncMock(return_value=True)
        self.send_message = AsyncMock()
        self.edit_message_caption = AsyncMock()
        self.edit_message_text = AsyncMock()
        self.edit_message_reply_markup = AsyncMock()


@pytest.fixture
def deps():
    conn = db.connect(":memory:")
    yield BotDeps(conn=conn, cfg=load_config(EXAMPLE), admin_chat_id=ADMIN, clock=lambda: NOW)
    conn.close()


def seed(conn, mlb_id="MLB1", niche="casa"):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title="Air Fryer", price=299.9, original_price=499.9,
        commission_pct=12, category_path=("MLB1574",), permalink="https://x", collected_at=NOW,
    ), now=NOW)
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=S.PENDING, score=70, breakdown={}, ref_price=299.9,
        decided_at=NOW, notified_at=NOW,
    ))


def chat(chat_id=ADMIN):
    return {"id": chat_id, "type": "private"}


def message(text, chat_id=ADMIN, **extra):
    entities = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {"message_id": 10, "date": 0, "chat": chat(chat_id), "text": text,
            "from": {"id": chat_id, "is_bot": False, "first_name": "M"},
            **({"entities": entities} if text.startswith("/") else {}), **extra}


def callback(data):
    return {"update_id": 2, "callback_query": {
        "id": "q1", "chat_instance": "c", "data": data,
        "from": {"id": ADMIN, "is_bot": False, "first_name": "M"},
        "message": {"message_id": 5, "date": 0, "chat": chat(), "text": "card"},
    }}


async def test_approve_button_approves_and_closes_the_card(deps):
    seed(deps.conn)
    bot = FakeBot()
    await handle_update(callback("a:MLB1:casa"), bot, deps)
    assert db.get_candidate(deps.conn, "MLB1", "casa").state is S.APPROVED
    bot.answer_callback_query.assert_awaited()
    assert "Aprovada" in bot.edit_message_text.await_args.kwargs["text"]


async def test_known_command_replies_and_unknown_is_ignored(deps):
    bot = FakeBot()
    await handle_update({"update_id": 3, "message": message("/stats")}, bot, deps)
    assert bot.send_message.await_args.kwargs["text"] == "Nenhum post enviado hoje."
    await handle_update({"update_id": 4, "message": message("/naoexiste")}, bot, deps)
    assert bot.send_message.await_count == 1


async def test_edit_flow_survives_between_updates(deps):
    seed(deps.conn)
    bot = FakeBot()
    await handle_update(callback("e:MLB1:casa"), bot, deps)
    assert db.get_setting(deps.conn, AWAITING_EDIT_KEY) == ["MLB1", "casa"]
    deps.awaiting_edit = None  # outro update, outra instância: só o banco lembra
    await handle_update({"update_id": 5, "message": message("Oferta {titulo_curto}")}, bot, deps)
    assert custom_caption(deps.conn, "MLB1", "casa").startswith("Oferta {titulo_curto}")
    assert db.get_setting(deps.conn, AWAITING_EDIT_KEY) is None


async def test_messages_from_other_chats_are_ignored(deps):
    bot = FakeBot()
    await handle_update({"update_id": 6, "message": message("/stats", chat_id=123)}, bot, deps)
    bot.send_message.assert_not_awaited()
