"""Ritmo de postagem por grupo: janela de horário, intervalo mínimo e limite diário."""

from datetime import UTC, date, datetime, time, timedelta

from ..config import Pacing
from ..models import TZ


def _local(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=TZ).astimezone(UTC)


def can_post(
    now: datetime,
    last_post_at: datetime | None,
    posts_today: int,
    pacing: Pacing,
    jitter_min: float = 0.0,
) -> tuple[bool, datetime | None]:
    """Se o grupo pode receber um post agora; se não, a partir de quando (UTC).

    `jitter_min` é a variação já sorteada para este intervalo (entre -jitter e +jitter),
    guardada por quem chama para não mudar a cada consulta.
    """
    local = now.astimezone(TZ)
    start, end = pacing.window
    tomorrow_open = _local(local.date() + timedelta(days=1), start)
    if local.time() < start:
        return False, _local(local.date(), start)
    if local.time() >= end or posts_today >= pacing.max_posts_per_day:
        return False, tomorrow_open
    if last_post_at is not None:
        earliest = last_post_at + timedelta(minutes=pacing.min_interval_min + jitter_min)
        if now < earliest:
            earliest_local = earliest.astimezone(TZ)
            if earliest_local.date() > local.date() or earliest_local.time() >= end:
                return False, tomorrow_open
            return False, earliest.astimezone(UTC)
    return True, None
