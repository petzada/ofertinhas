"""Estoque de ofertas de cada grupo e até quando ele alimenta o ritmo de posts do dia.

Com o backend na nuvem, o PC só precisa ficar ligado enquanto a extensão coleta e gera os
links. O que já tem link é o estoque: a nuvem gera o card e posta sozinha. Mas cada oferta
vale `max_offer_age_hours` depois da última coleta em que apareceu, então o estoque acaba
quando os próximos horários de post do dia ficam sem oferta válida. É isso que se calcula
aqui, simulando os horários com a mesma regra de ritmo do envio.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import db
from .alerts import notify_throttled
from .config import AppConfig, NicheConfig, Pacing
from .models import TZ, CandidateState
from .publisher.pacing import can_post
from .publisher.publish import destination_groups, pacing_key

S = CandidateState
READY = (S.LINKED, S.RENDERED, S.QUEUED)  # já têm link: a nuvem posta sem o PC
WAITING_LINK = (S.APPROVED,)  # dependem da extensão gerar o link
ALERT_LEAD = timedelta(hours=1)
ALERT_EVERY = timedelta(hours=2)
LINK_MINUTES = 1  # ~1 link por minuto com o portal aberto (intervalo de 30 a 90 s)


@dataclass(frozen=True)
class GroupStock:
    key: str
    ready: int
    waiting_links: int
    posts_today: int
    max_posts: int
    ends_at: datetime | None  # primeiro horário de post do dia sem oferta; None = cobre o dia
    ends_at_with_links: datetime | None  # o mesmo, se as que esperam link ganharem link agora

    def as_dict(self) -> dict:
        def iso(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        return {"ready": self.ready, "waiting_links": self.waiting_links,
                "posts_today": self.posts_today, "max_posts": self.max_posts,
                "ends_at": iso(self.ends_at), "ends_at_with_links": iso(self.ends_at_with_links)}


def post_slots(now: datetime, last_post_at: datetime | None, posts_today: int, pacing: Pacing,
               jitter_min: float = 0.0) -> list[datetime]:
    """Próximos horários de post até o fim da janela de hoje (horário de São Paulo)."""
    local = now.astimezone(TZ)
    day_end = datetime.combine(local.date(), pacing.window[1], tzinfo=TZ)
    slots: list[datetime] = []
    t, last, count, jitter = now, last_post_at, posts_today, jitter_min
    while t < day_end:
        allowed, at = can_post(t, last, count, pacing, jitter)
        if not allowed:
            if at is None or at >= day_end:
                break
            t = at
            continue
        slots.append(t)
        last, count, jitter = t, count + 1, 0.0
        t = t + timedelta(minutes=pacing.min_interval_min)
    return slots


def _covered_until(slots: list[datetime], expiries: list[datetime]) -> datetime | None:
    """Primeiro horário sem oferta válida; cada post gasta a que vence primeiro."""
    left = sorted(expiries)
    for slot in slots:
        while left and left[0] < slot:
            left.pop(0)  # venceu antes de chegar a vez dela
        if not left:
            return slot
        left.pop(0)
    return None


def _expiries(conn: sqlite3.Connection, niches: list[NicheConfig],
              states: tuple[CandidateState, ...], now: datetime) -> list[datetime]:
    out = []
    for niche in niches:
        max_age = timedelta(hours=niche.max_offer_age_hours)
        for state in states:
            for cand in db.candidates_by_state(conn, state, niche=niche.name):
                seen = db.get_offer(conn, cand.mlb_id).last_seen_at
                if seen and seen + max_age > now:
                    out.append(seen + max_age)
    return out


def group_stock(conn: sqlite3.Connection, cfg: AppConfig, now: datetime,
                dry_run: bool) -> list[GroupStock]:
    report = []
    for (tg_chat, wa_jid), niches in destination_groups(conn, cfg).items():
        if tg_chat is None and wa_jid is None:
            continue
        key = pacing_key(tg_chat, wa_jid, dry_run)
        pacing = niches[0].pacing if tg_chat is not None else (
            niches[0].whatsapp_pacing or niches[0].pacing)
        posts_today = db.posts_today(conn, key, now)
        slots = post_slots(now, db.last_post_at(conn, key), posts_today, pacing,
                           db.get_setting(conn, f"jitter:{key}", 0.0))
        ready = _expiries(conn, niches, READY, now)
        waiting = _expiries(conn, niches, WAITING_LINK, now)
        report.append(GroupStock(
            key=key, ready=len(ready), waiting_links=len(waiting), posts_today=posts_today,
            max_posts=pacing.max_posts_per_day, ends_at=_covered_until(slots, ready),
            ends_at_with_links=_covered_until(slots, ready + waiting),
        ))
    return report


async def alert_low_stock(conn: sqlite3.Connection, cfg: AppConfig, notify, now: datetime,
                          dry_run: bool) -> int:
    """Avisa o admin quando o estoque de um grupo acaba em menos de uma hora."""
    sent = 0
    for g in group_stock(conn, cfg, now, dry_run):
        if g.ends_at is None or g.ends_at - now > ALERT_LEAD:
            continue
        at = g.ends_at.astimezone(TZ).strftime("%H:%M")
        when = "já está sem ofertas para postar" if g.ends_at <= now else f"acaba às {at}"
        minutes = max(g.waiting_links, 10) * LINK_MINUTES
        text = (
            f"⏰ O estoque do grupo {when} ({g.ready} prontas, {g.waiting_links} esperando "
            f"link; {g.posts_today}/{g.max_posts} posts hoje). Abra o Brave e clique em "
            f"Coletar agora no Ofertinhas. Deixe aberto uns {minutes} min, até o popup "
            "dizer que pode fechar."
        )
        sent += await notify_throttled(conn, notify, f"stock-low:{g.key}", text, now,
                                       ALERT_EVERY)
    return sent
