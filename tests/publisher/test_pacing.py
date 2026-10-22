from datetime import UTC, datetime, timedelta

from ofertinhas.config import Pacing
from ofertinhas.publisher.pacing import can_post

P = Pacing()  # 25 min, janela 08:00–23:00, 25 posts/dia


def sp(day, hour, minute=0):
    """Horário de São Paulo (UTC-3) em UTC."""
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC) + timedelta(hours=3)


def test_allowed_inside_window_without_previous_post():
    assert can_post(sp(22, 10), None, 0, P) == (True, None)


def test_before_window_waits_until_opening():
    assert can_post(sp(22, 7, 30), None, 0, P) == (False, sp(22, 8))


def test_after_window_waits_until_next_day():
    assert can_post(sp(22, 23, 0), None, 0, P) == (False, sp(23, 8))


def test_min_interval_with_jitter():
    last = sp(22, 10)
    assert can_post(sp(22, 10, 20), last, 1, P, jitter_min=3) == (False, sp(22, 10, 28))
    assert can_post(sp(22, 10, 28), last, 1, P, jitter_min=3) == (True, None)
    assert can_post(sp(22, 10, 22), last, 1, P, jitter_min=-3) == (True, None)


def test_daily_limit_waits_until_tomorrow():
    assert can_post(sp(22, 15), sp(22, 14), 25, P) == (False, sp(23, 8))


def test_interval_that_crosses_window_end_moves_to_next_day():
    assert can_post(sp(22, 22, 50), sp(22, 22, 45), 3, P) == (False, sp(23, 8))


def test_day_turnover_uses_sao_paulo_time():
    # 00:30 em SP do dia 23 ainda é 03:30 UTC; a janela só abre às 08:00 locais.
    assert can_post(sp(23, 0, 30), sp(22, 22), 25, P) == (False, sp(23, 8))
