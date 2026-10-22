"""Etapa de postagem: a melhor oferta pronta de cada grupo, respeitando o ritmo do grupo.

Nichos com o mesmo destino (mesmo grupo do Telegram/WhatsApp) dividem a fila e o ritmo: a vez
é da melhor oferta pronta entre eles, com as aprovadas à mão na frente. O post sai no Telegram
e, com `whatsapp_enabled`, em seguida no WhatsApp.

Em modo de teste (`dry_run`), o Telegram vai para o chat do admin com o selo de teste, o
WhatsApp não é usado e o ritmo é contado à parte (`dry-run:<grupo>`).
"""

import asyncio
import dataclasses
import logging
import random
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from pathlib import Path

from .. import db
from ..alerts import notify_throttled
from ..cardstore import CardStore, DiskCards
from ..config import AppConfig, NicheConfig
from ..creative.format import to_telegram_html, to_whatsapp
from ..models import Candidate, CandidateState
from .cardhost import CardHostError
from .pacing import can_post
from .telegram import TelegramError
from .whatsapp import WhatsAppError

log = logging.getLogger(__name__)
S = CandidateState
RETRY_AFTER_FAILURE = timedelta(minutes=10)
ALERT_EVERY = timedelta(minutes=30)
WHATSAPP_TYPING_S = (3, 8)
_DISK = DiskCards(Path())


def _next_in_group(
    conn: sqlite3.Connection, niches: list[NicheConfig], now: datetime
) -> tuple[Candidate, NicheConfig] | None:
    """Próxima oferta do grupo, expirando as que sumiram da coleta.

    Automáticas primeiro (passaram na regra mais dura); as aprovadas à mão (card mostrado)
    completam a fila depois. Dentro de cada grupo, a maior nota.
    """
    by_name = {n.name: n for n in niches}
    while True:
        ready = [c for name in by_name for c in db.candidates_by_state(conn, S.RENDERED, name)]
        if not ready:
            return None
        ready.sort(key=lambda c: (c.notified_at is not None, -c.score))
        cand = ready[0]
        niche = by_name[cand.niche]
        offer = db.get_offer(conn, cand.mlb_id)
        if offer.last_seen_at and now - offer.last_seen_at <= timedelta(
            hours=niche.max_offer_age_hours
        ):
            return cand, niche
        db.save_candidate(conn, dataclasses.replace(cand, state=S.EXPIRED))


async def publish_due(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    *,
    telegram,
    whatsapp=None,
    card_host=None,
    admin_chat_id: int,
    dry_run: bool,
    now: datetime,
    notify: Callable[[str], Awaitable[None]],
    rng: random.Random | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    card_store: CardStore | None = None,
) -> list[str]:
    """Posta no máximo uma oferta por grupo e devolve os MLB postados.

    Sem `card_store`, o `card_path` da candidata é um arquivo em disco."""
    from ..pipeline import niche_configs  # evita import circular

    rng = rng or random.Random()
    groups: dict[tuple, list[NicheConfig]] = {}
    for niche in niche_configs(conn, cfg).values():
        if not niche.paused:
            groups.setdefault(niche.destination(), []).append(niche)

    posted = []
    for (tg_chat, wa_jid), members in groups.items():
        primary = str(tg_chat) if tg_chat is not None else wa_jid
        key = f"dry-run:{primary}" if dry_run else primary
        use_whatsapp = bool(cfg.whatsapp_enabled and wa_jid and whatsapp and not dry_run)
        if tg_chat is None and not use_whatsapp and not dry_run:
            continue

        retry_at = db.get_setting(conn, f"retry_at:{key}")
        if retry_at and now < datetime.fromisoformat(retry_at):
            continue
        pacing = members[0].pacing
        if dry_run:  # teste vale a qualquer hora; nos grupos, post de madrugada ninguém vê
            pacing = pacing.model_copy(update={"window": (time(0, 0), time(23, 59, 59))})
        allowed, _ = can_post(
            now, db.last_post_at(conn, key), db.posts_today(conn, key, now), pacing,
            db.get_setting(conn, f"jitter:{key}", 0.0),
        )
        if not allowed:
            continue
        found = _next_in_group(conn, members, now)
        if found is None:
            continue
        cand, niche = found
        offer = db.get_offer(conn, cand.mlb_id)
        png = await (card_store or _DISK).load(cand.card_path)

        sent_any = False
        if tg_chat is not None or dry_run:
            caption = to_telegram_html(cand.caption)
            if dry_run:
                caption = f"🧪 <b>TESTE • {niche.name}</b>\n\n{caption}"
            target = str(admin_chat_id) if dry_run else str(tg_chat)
            try:
                message_id = await telegram.send_photo(target, png, caption)
            except TelegramError as e:
                db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="telegram",
                               chat=key, status="failed", sent_at=now, error=str(e))
                await notify_throttled(
                    conn, notify, f"publish-fail:{key}",
                    f"⚠️ Não consegui postar no Telegram ({niche.name}): {e}. "
                    "Tento de novo em 10 min.", now, ALERT_EVERY,
                )
            else:
                db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="telegram",
                               chat=key, status="sent", sent_at=now, message_id=message_id,
                               price=offer.price)
                sent_any = True

        if use_whatsapp and card_host is None:
            await notify_throttled(
                conn, notify, "whatsapp-no-host",
                "⚠️ WhatsApp ligado, mas falta R2_API_TOKEN no .env para publicar a imagem.",
                now, ALERT_EVERY,
            )
        elif use_whatsapp:
            # Sem Telegram no grupo, o WhatsApp é quem conta para o ritmo.
            wa_chat = key if tg_chat is None else wa_jid
            try:
                media_url = await card_host.upload(f"cards/{cand.mlb_id}-{cand.niche}.png", png)
                await whatsapp.send_presence(wa_jid)
                await sleep(rng.uniform(*WHATSAPP_TYPING_S))
                message_id = await whatsapp.send_image(wa_jid, media_url,
                                                       to_whatsapp(cand.caption))
            except (WhatsAppError, CardHostError) as e:
                db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="whatsapp",
                               chat=wa_chat, status="failed", sent_at=now, error=str(e))
                await notify_throttled(
                    conn, notify, f"publish-fail-wa:{wa_jid}",
                    f"⚠️ Não consegui postar no WhatsApp ({niche.name}): {e}.", now, ALERT_EVERY,
                )
            else:
                db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="whatsapp",
                               chat=wa_chat, status="sent", sent_at=now, message_id=message_id,
                               price=offer.price)
                sent_any = True

        if not sent_any:
            db.set_setting(conn, f"retry_at:{key}", (now + RETRY_AFTER_FAILURE).isoformat())
            continue
        db.save_candidate(conn, dataclasses.replace(
            cand, state=S.POSTED, decided_at=now, ref_price=offer.price,
        ))
        spread = niche.pacing.jitter_min
        db.set_setting(conn, f"jitter:{key}", rng.uniform(-spread, spread))
        posted.append(cand.mlb_id)
    return posted
