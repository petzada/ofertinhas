from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofertinhas import db
from ofertinhas.config import load_config
from ofertinhas.jobs import SCHEDULE, is_due
from ofertinhas.publisher.telegram import TelegramError
from ofertinhas.status import LAST_COLLECT_KEY, STATUS_MESSAGE_KEY, pin_status, status_text

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 10, 22, 16, tzinfo=UTC)  # 13:00 em São Paulo


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def telegram():
    return SimpleNamespace(send_message=AsyncMock(return_value="50"), edit_message=AsyncMock(),
                           pin_message=AsyncMock())


def test_status_text_has_queue_collect_whatsapp_and_version(conn):
    cfg = load_config(ROOT / "config.example.yaml")
    db.set_setting(conn, LAST_COLLECT_KEY, (NOW - timedelta(minutes=40)).isoformat())
    db.set_setting(conn, "price_check:2026-10-22", {"inflated": 3, "last": []})
    db.set_setting(conn, db.EXTENSION_PAUSED_KEY, {"reason": "captcha"})
    text = status_text(conn, cfg, NOW, dry_run=False, whatsapp_state="open",
                       version="abc1234 • config 1a2b")
    assert "atualizado às 13:00" in text and "Posts reais" in text
    assert "posts hoje: 0/32" in text and "Cards para você aprovar: 0" in text
    assert "Última coleta: 12:20 (há 40 min)" in text
    assert "Extensão pausada: captcha" in text
    assert "Descontos inflados barrados hoje: 3" in text
    assert "WhatsApp: open" in text and "abc1234" in text


async def test_first_status_is_sent_silently_and_pinned(conn):
    tg = telegram()
    assert await pin_status(conn, tg, 777, "oi") == "sent"
    tg.send_message.assert_awaited_once_with(777, "oi", silent=True)
    tg.pin_message.assert_awaited_once_with(777, "50")
    assert db.get_setting(conn, STATUS_MESSAGE_KEY) == {"chat": "777", "message_id": "50"}


async def test_next_status_edits_the_pinned_message(conn):
    tg = telegram()
    db.set_setting(conn, STATUS_MESSAGE_KEY, {"chat": "777", "message_id": "50"})
    assert await pin_status(conn, tg, 777, "novo") == "edited"
    tg.edit_message.assert_awaited_once_with(777, "50", "novo")
    tg.send_message.assert_not_awaited()


async def test_deleted_status_message_is_replaced(conn):
    tg = telegram()
    tg.edit_message.side_effect = TelegramError("message to edit not found", retryable=False)
    db.set_setting(conn, STATUS_MESSAGE_KEY, {"chat": "777", "message_id": "49"})
    assert await pin_status(conn, tg, 777, "novo") == "sent"
    tg.pin_message.assert_awaited_once_with(777, "50")


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        ((11, 0), {"status"}),  # 08:00 em São Paulo
        ((16, 0), {"status"}),
        ((7, 30), {"prune"}),
        ((7, 0), {"backup"}),
        ((16, 1), set()),
    ],
)
def test_daily_jobs_run_at_sao_paulo_times(utc, expected):
    now = datetime(2026, 10, 22, *utc, tzinfo=UTC)
    daily = {"status", "prune", "backup"}
    assert {n for n in daily if is_due(SCHEDULE[n], now)} == expected


def test_every_minute_jobs_follow_the_clock():
    at = datetime(2026, 10, 22, 15, 5, tzinfo=UTC)
    assert is_due(SCHEDULE["stock_alert"], at) and not is_due(SCHEDULE["expire"], at)
    assert is_due(SCHEDULE["expire"], at.replace(minute=15))
