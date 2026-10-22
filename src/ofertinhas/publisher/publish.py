"""Etapa de postagem: a melhor oferta pronta de cada nicho, respeitando o ritmo do grupo.

Em modo de teste (`dry_run`), tudo vai para o chat do admin com o selo de teste, e o ritmo é
contado à parte (`dry-run:<nicho>`) para não se misturar aos posts reais.
"""

import dataclasses
import logging
import random
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from pathlib import Path

from .. import db
from ..alerts import notify_throttled
from ..config import AppConfig
from ..creative.format import to_telegram_html
from ..models import CandidateState
from .pacing import can_post
from .queue import next_for_niche
from .telegram import TelegramError

log = logging.getLogger(__name__)
S = CandidateState
RETRY_AFTER_FAILURE = timedelta(minutes=10)


def _key(name: str, chat: str, dry_run: bool) -> str:
    return f"dry-run:{name}" if dry_run else chat


async def publish_due(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    *,
    telegram,
    admin_chat_id: int,
    dry_run: bool,
    now: datetime,
    notify: Callable[[str], Awaitable[None]],
    rng: random.Random | None = None,
) -> list[str]:
    """Posta no máximo uma oferta por nicho e devolve os MLB postados."""
    from ..pipeline import niche_configs  # evita import circular

    rng = rng or random.Random()
    posted = []
    for name, niche in niche_configs(conn, cfg).items():
        if niche.paused:
            continue
        chat = str(admin_chat_id) if dry_run else (
            str(niche.telegram_chat_id) if niche.telegram_chat_id is not None else None
        )
        if chat is None:
            continue  # nicho só de WhatsApp: entra quando o envio ao WhatsApp existir
        key = _key(name, chat, dry_run)

        retry_at = db.get_setting(conn, f"retry_at:{key}")
        if retry_at and now < datetime.fromisoformat(retry_at):
            continue
        jitter = db.get_setting(conn, f"jitter:{key}", 0.0)
        pacing = niche.pacing
        if dry_run:  # teste vale a qualquer hora; nos grupos, post de madrugada ninguém vê
            pacing = pacing.model_copy(update={"window": (time(0, 0), time(23, 59, 59))})
        allowed, _ = can_post(
            now, db.last_post_at(conn, key), db.posts_today(conn, key, now), pacing, jitter
        )
        if not allowed:
            continue

        cand = next_for_niche(conn, name)
        while cand is not None:
            offer = db.get_offer(conn, cand.mlb_id)
            max_age = timedelta(hours=niche.max_offer_age_hours)
            if offer.last_seen_at and now - offer.last_seen_at <= max_age:
                break
            db.save_candidate(conn, dataclasses.replace(cand, state=S.EXPIRED))
            cand = next_for_niche(conn, name)
        if cand is None:
            continue

        caption = to_telegram_html(cand.caption)
        if dry_run:
            caption = f"🧪 <b>TESTE • {name}</b>\n\n{caption}"
        try:
            message_id = await telegram.send_photo(chat, Path(cand.card_path).read_bytes(), caption)
        except (TelegramError, OSError) as e:
            db.record_post(conn, mlb_id=cand.mlb_id, niche=name, channel="telegram", chat=key,
                           status="failed", sent_at=now, error=str(e))
            db.set_setting(conn, f"retry_at:{key}", (now + RETRY_AFTER_FAILURE).isoformat())
            await notify_throttled(
                conn, notify, f"publish-fail:{key}",
                f"⚠️ Não consegui postar no Telegram ({name}): {e}. Tento de novo em 10 min.",
                now, timedelta(minutes=30),
            )
            continue

        db.record_post(conn, mlb_id=cand.mlb_id, niche=name, channel="telegram", chat=key,
                       status="sent", sent_at=now, message_id=message_id, price=offer.price)
        db.save_candidate(conn, dataclasses.replace(
            cand, state=S.POSTED, decided_at=now, ref_price=offer.price,
        ))
        spread = niche.pacing.jitter_min
        db.set_setting(conn, f"jitter:{key}", rng.uniform(-spread, spread))
        if cfg.whatsapp_enabled:
            log.warning("whatsapp_enabled está ligado, mas o envio ao WhatsApp ainda não existe")
        posted.append(cand.mlb_id)
    return posted
