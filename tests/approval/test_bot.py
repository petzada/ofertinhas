from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofertinhas import db
from ofertinhas.approval.actions import custom_caption
from ofertinhas.approval.bot import (
    BotDeps,
    on_callback,
    on_command,
    on_text,
    send_pending_cards,
)
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
EXAMPLE = Path(__file__).parents[2] / "config.example.yaml"
ADMIN = 777
S = CandidateState


@pytest.fixture
def deps():
    conn = db.connect(":memory:")
    yield BotDeps(conn=conn, cfg=load_config(EXAMPLE), admin_chat_id=ADMIN, clock=lambda: NOW)
    conn.close()


def seed(conn, mlb_id="MLB1", image_url="https://img/1.webp", state=S.PENDING, niche="casa"):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title="Air Fryer", price=299.9, original_price=499.9,
        commission_pct=12, category_path=("MLB1574",), permalink="https://x",
        image_url=image_url, collected_at=NOW,
    ), now=NOW)
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=state, score=70, breakdown={"commission_pct": 20.0},
        ref_price=299.9, decided_at=NOW,
    ))


@pytest.mark.parametrize("flow_state", [S.APPROVED, S.LINKED, S.RENDERED])
async def test_cards_wait_while_the_group_has_automatic_offers(deps, flow_state):
    seed(deps.conn, "MLB1")  # pendente de casa
    seed(deps.conn, "MLB2", state=flow_state)  # automática de casa ainda no fluxo
    bot = fake_bot()
    assert await send_pending_cards(bot, deps) == 0
    with deps.conn:
        deps.conn.execute("UPDATE candidates SET state = 'posted' WHERE mlb_id = 'MLB2'")
    assert await send_pending_cards(bot, deps) == 1  # fila automática vazia: vai o bônus


async def test_cards_of_other_groups_are_not_held(deps):
    seed(deps.conn, "MLB1", niche="tech")  # tech tem outro grupo no exemplo
    seed(deps.conn, "MLB2", state=S.RENDERED)  # automática de casa
    assert await send_pending_cards(fake_bot(), deps) == 1


def fake_bot():
    return SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())


def query(data, chat_id=ADMIN, photo=True):
    message = SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        photo=[object()] if photo else [],
        caption_html="card", text_html="card",
        reply_text=AsyncMock(),
    )
    q = SimpleNamespace(
        data=data, message=message, answer=AsyncMock(), edit_message_caption=AsyncMock(),
        edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock(),
    )
    return SimpleNamespace(callback_query=q)


def text_update(text, chat_id=ADMIN):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=chat_id))


async def test_send_pending_cards_once(deps):
    seed(deps.conn, "MLB1")
    seed(deps.conn, "MLB2", image_url=None)
    bot = fake_bot()
    assert await send_pending_cards(bot, deps) == 2
    assert bot.send_photo.await_count == 1 and bot.send_message.await_count == 1
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["chat_id"] == ADMIN and kwargs["photo"] == "https://img/1.webp"
    assert kwargs["parse_mode"] == "HTML" and kwargs["reply_markup"] is not None
    assert await send_pending_cards(bot, deps) == 0  # já notificadas


async def test_pending_cards_are_sent_in_small_batches(deps):
    for i in range(7):
        seed(deps.conn, f"MLB{i}")
    bot = fake_bot()
    assert await send_pending_cards(bot, deps, limit=5) == 5
    assert await send_pending_cards(bot, deps, limit=5) == 2


async def test_photo_failure_falls_back_to_text(deps):
    seed(deps.conn)
    bot = fake_bot()
    bot.send_photo.side_effect = RuntimeError("bad photo url")
    assert await send_pending_cards(bot, deps) == 1
    assert bot.send_message.await_count == 1


async def test_approve_button(deps):
    seed(deps.conn)
    upd = query("a:MLB1:casa")
    await on_callback(deps, upd)
    assert db.get_candidate(deps.conn, "MLB1", "casa").state is S.APPROVED
    q = upd.callback_query
    q.answer.assert_awaited()
    kwargs = q.edit_message_caption.await_args.kwargs
    assert "Aprovada" in kwargs["caption"] and kwargs["reply_markup"] is None


async def test_reject_button_on_text_card(deps):
    seed(deps.conn)
    upd = query("r:MLB1:casa", photo=False)
    await on_callback(deps, upd)
    assert db.get_candidate(deps.conn, "MLB1", "casa").state is S.REJECTED
    assert upd.callback_query.edit_message_text.await_count == 1


async def test_buttons_from_other_chats_are_ignored(deps):
    seed(deps.conn)
    await on_callback(deps, query("a:MLB1:casa", chat_id=123))
    assert db.get_candidate(deps.conn, "MLB1", "casa").state is S.PENDING


async def test_action_error_shows_alert(deps):
    seed(deps.conn, state=S.REJECTED)
    upd = query("a:MLB1:casa")
    await on_callback(deps, upd)
    assert upd.callback_query.answer.await_args.kwargs.get("show_alert") is True


async def test_edit_flow(deps):
    seed(deps.conn)
    upd = query("e:MLB1:casa")
    await on_callback(deps, upd)
    assert deps.awaiting_edit == ("MLB1", "casa")
    reply = text_update("Achado do dia: {titulo_curto}")
    await on_text(deps, reply)
    assert custom_caption(deps.conn, "MLB1", "casa").startswith("Achado do dia")
    assert deps.awaiting_edit is None


async def test_text_without_pending_edit_is_ignored(deps):
    upd = text_update("oi")
    await on_text(deps, upd)
    upd.message.reply_text.assert_not_awaited()


async def test_change_niche_flow(deps):
    seed(deps.conn)
    upd = query("n:MLB1:casa")
    await on_callback(deps, upd)
    upd.callback_query.edit_message_reply_markup.assert_awaited()
    upd = query("m:MLB1:casa:tech")
    await on_callback(deps, upd)
    assert db.get_candidate(deps.conn, "MLB1", "tech").state is S.PENDING
    assert db.get_candidate(deps.conn, "MLB1", "casa") is None


async def test_commands_only_for_admin_except_chatid(deps):
    other = text_update("/stats", chat_id=123)
    await on_command(deps, other, "stats", [])
    other.message.reply_text.assert_not_awaited()

    chatid = text_update("/chatid", chat_id=123)
    await on_command(deps, chatid, "chatid", [])
    assert "123" in chatid.message.reply_text.await_args.args[0]

    admin = text_update("/stats")
    await on_command(deps, admin, "stats", [])
    admin.message.reply_text.assert_awaited()


def test_build_application_registers_handlers(deps):
    from ofertinhas.approval.bot import build_application

    app = build_application("123456:TESTE-token-falso", deps)
    assert sum(len(h) for h in app.handlers.values()) == 3


async def test_cancel_command_clears_pending_edit(deps):
    deps.awaiting_edit = ("MLB1", "casa")
    await on_command(deps, text_update("/cancelar"), "cancelar", [])
    assert deps.awaiting_edit is None
