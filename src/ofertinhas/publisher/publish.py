"""Etapa de postagem: a melhor oferta pronta de cada grupo, no ritmo de cada canal.

Nichos com o mesmo destino (mesmo grupo do Telegram/WhatsApp) dividem a fila. Cada canal tem
relógio, janela e espera após falha próprios: o Telegram usa `pacing` e posta a melhor oferta
pronta que ainda não saiu (aprovadas à mão por último); o WhatsApp usa `whatsapp_pacing` (ou
o mesmo `pacing`, se não houver) e posta a melhor oferta fresca do período que ainda não foi
a ele, mesmo que já tenha saído no Telegram. Assim o WhatsApp recebe menos posts, só os
melhores. Com `whatsapp_enabled` desligado, nada vai ao WhatsApp.

Em modo de teste (`dry_run`), o Telegram vai para o chat do admin com o selo de teste e o
ritmo é contado à parte (`dry-run:<grupo>`). O WhatsApp só é usado no teste se houver um
destino de teste (`whatsapp_test_jid`, por exemplo a conversa com o próprio número); nunca
vai para o grupo.
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
from ..config import AppConfig, NicheConfig, Pacing
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


def destination_groups(
    conn: sqlite3.Connection, cfg: AppConfig
) -> dict[tuple[int | None, str | None], list[NicheConfig]]:
    """Nichos ativos agrupados por destino (Telegram, WhatsApp): cada grupo é uma fila."""
    from ..pipeline import niche_configs  # evita import circular

    groups: dict[tuple, list[NicheConfig]] = {}
    for niche in niche_configs(conn, cfg).values():
        if not niche.paused:
            groups.setdefault(niche.destination(), []).append(niche)
    return groups


def pacing_key(tg_chat: int | None, wa_jid: str | None, dry_run: bool) -> str:
    """Chave do ritmo do grupo nos posts: o Telegram, ou o WhatsApp quando não há Telegram."""
    primary = str(tg_chat) if tg_chat is not None else wa_jid
    return f"dry-run:{primary}" if dry_run else primary


def _next_in_group(
    conn: sqlite3.Connection, niches: list[NicheConfig], now: datetime,
    only_mlb: str | None = None,
) -> tuple[Candidate, NicheConfig] | None:
    """Próxima oferta do grupo, expirando as que sumiram da coleta.

    Automáticas primeiro (passaram na regra mais dura); as aprovadas à mão (card mostrado)
    completam a fila depois. Dentro de cada grupo, a maior nota. Com `only_mlb`, só essa.
    """
    by_name = {n.name: n for n in niches}
    while True:
        ready = [c for name in by_name for c in db.candidates_by_state(conn, S.RENDERED, name)
                 if only_mlb is None or c.mlb_id == only_mlb]
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


def _best_for_whatsapp(
    conn: sqlite3.Connection, niches: list[NicheConfig], now: datetime, chat: str,
    only_mlb: str | None = None,
) -> tuple[Candidate, NicheConfig] | None:
    """A melhor oferta fresca do grupo (pronta ou já postada no Telegram) que ainda não foi a
    este chat do WhatsApp dentro do cooldown de repost."""
    best = None
    for niche in niches:
        max_age = timedelta(hours=niche.max_offer_age_hours)
        since = now - timedelta(days=niche.repost_cooldown_days)
        for state in (S.RENDERED, S.POSTED):
            for cand in db.candidates_by_state(conn, state, niche.name):
                if only_mlb is not None and cand.mlb_id != only_mlb:
                    continue
                if state is S.POSTED and now - cand.decided_at > max_age:
                    continue  # postada no Telegram há tempo demais: não é mais "do período"
                seen = db.get_offer(conn, cand.mlb_id).last_seen_at
                if seen is None or now - seen > max_age:
                    continue
                if db.sent_to_chat_since(conn, cand.mlb_id, chat, since):
                    continue
                rank = (cand.notified_at is not None, -cand.score)
                if best is None or rank < best[0]:
                    best = (rank, cand, niche)
    return (best[1], best[2]) if best else None


def _due(conn: sqlite3.Connection, key: str, pacing: Pacing, now: datetime, dry_run: bool,
         force: bool) -> bool:
    if force:
        return True
    retry_at = db.get_setting(conn, f"retry_at:{key}")
    if retry_at and now < datetime.fromisoformat(retry_at):
        return False
    if dry_run:  # teste vale a qualquer hora; nos grupos, post de madrugada ninguém vê
        pacing = pacing.model_copy(update={"window": (time(0, 0), time(23, 59, 59))})
    allowed, _ = can_post(now, db.last_post_at(conn, key), db.posts_today(conn, key, now),
                          pacing, db.get_setting(conn, f"jitter:{key}", 0.0))
    return allowed


def _next_jitter(conn: sqlite3.Connection, key: str, pacing: Pacing,
                 rng: random.Random) -> None:
    """Variação do próximo intervalo (ex.: 45 ± 15 min = 30 a 60), sorteada uma vez."""
    db.set_setting(conn, f"jitter:{key}", rng.uniform(-pacing.jitter_min, pacing.jitter_min))


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
    whatsapp_test_jid: str | None = None,
    force: bool = False,
    only_mlb: str | None = None,
) -> list[str]:
    """Posta no máximo uma oferta por canal de cada grupo e devolve os MLB postados.

    `force` é o post avulso pedido pelo admin: ignora janela, intervalo e espera após falha
    só desta vez (o post conta no ritmo e no limite do dia como qualquer outro). Com
    `only_mlb`, posta só essa oferta (com card pronto), no grupo do nicho dela.

    Sem `card_store`, o `card_path` da candidata é um arquivo em disco."""
    rng = rng or random.Random()
    store = card_store or _DISK
    posted: list[str] = []
    for (tg_chat, wa_jid), members in destination_groups(conn, cfg).items():
        if tg_chat is not None or dry_run:
            mlb = await _telegram_turn(
                conn, members, tg_chat, wa_jid, telegram=telegram, store=store,
                admin_chat_id=admin_chat_id, dry_run=dry_run, now=now, notify=notify, rng=rng,
                force=force, only_mlb=only_mlb,
            )
            if mlb:
                posted.append(mlb)
        wa_target = whatsapp_test_jid if dry_run else wa_jid
        if not (cfg.whatsapp_enabled and wa_jid and whatsapp and wa_target):
            continue
        if card_host is None:
            await notify_throttled(
                conn, notify, "whatsapp-no-host",
                "⚠️ WhatsApp ligado, mas falta R2_API_TOKEN no .env para publicar a imagem.",
                now, ALERT_EVERY,
            )
            continue
        mlb = await _whatsapp_turn(
            conn, members, wa_target, whatsapp=whatsapp, card_host=card_host, store=store,
            dry_run=dry_run, now=now, notify=notify, rng=rng, sleep=sleep, force=force,
            only_mlb=only_mlb, owns_queue=tg_chat is None,
        )
        if mlb and mlb not in posted:
            posted.append(mlb)
    return posted


async def _telegram_turn(conn, members, tg_chat, wa_jid, *, telegram, store, admin_chat_id,
                         dry_run, now, notify, rng, force, only_mlb) -> str | None:
    key = pacing_key(tg_chat, wa_jid, dry_run)
    pacing = members[0].pacing
    if not _due(conn, key, pacing, now, dry_run, force):
        return None
    found = _next_in_group(conn, members, now, only_mlb)
    if found is None:
        return None
    cand, niche = found
    offer = db.get_offer(conn, cand.mlb_id)
    caption = to_telegram_html(cand.caption)
    if dry_run:
        caption = f"🧪 <b>TESTE • {niche.name}</b>\n\n{caption}"
    target = str(admin_chat_id) if dry_run else str(tg_chat)
    try:
        message_id = await telegram.send_photo(target, await store.load(cand.card_path), caption)
    except TelegramError as e:
        db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="telegram",
                       chat=key, status="failed", sent_at=now, error=str(e))
        db.set_setting(conn, f"retry_at:{key}", (now + RETRY_AFTER_FAILURE).isoformat())
        await notify_throttled(
            conn, notify, f"publish-fail:{key}",
            f"⚠️ Não consegui postar no Telegram ({niche.name}): {e}. "
            "Tento de novo em 10 min.", now, ALERT_EVERY,
        )
        return None
    db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="telegram", chat=key,
                   status="sent", sent_at=now, message_id=message_id, price=offer.price)
    db.save_candidate(conn, dataclasses.replace(
        cand, state=S.POSTED, decided_at=now, ref_price=offer.price,
    ))
    _next_jitter(conn, key, pacing, rng)
    return cand.mlb_id


async def _whatsapp_turn(conn, members, wa_target, *, whatsapp, card_host, store, dry_run, now,
                         notify, rng, sleep, force, only_mlb, owns_queue) -> str | None:
    """`owns_queue`: o grupo não tem Telegram, então o post do WhatsApp tira a oferta da fila."""
    key = f"dry-run:{wa_target}" if dry_run else wa_target
    pacing = members[0].whatsapp_pacing or members[0].pacing
    if not _due(conn, key, pacing, now, dry_run, force):
        return None
    found = _best_for_whatsapp(conn, members, now, key, only_mlb)
    if found is None:
        return None
    cand, niche = found
    offer = db.get_offer(conn, cand.mlb_id)
    caption = to_whatsapp(cand.caption)
    if dry_run:
        caption = f"🧪 *TESTE • {niche.name}*\n\n{caption}"
    try:
        png = await store.load(cand.card_path)
        media_url = await card_host.upload(f"cards/{cand.mlb_id}-{cand.niche}.png", png)
        await whatsapp.send_presence(wa_target)
        await sleep(rng.uniform(*WHATSAPP_TYPING_S))
        message_id = await whatsapp.send_image(wa_target, media_url, caption)
    except (WhatsAppError, CardHostError) as e:
        db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="whatsapp",
                       chat=key, status="failed", sent_at=now, error=str(e))
        db.set_setting(conn, f"retry_at:{key}", (now + RETRY_AFTER_FAILURE).isoformat())
        await notify_throttled(
            conn, notify, f"publish-fail-wa:{wa_target}",
            f"⚠️ Não consegui postar no WhatsApp ({niche.name}): {e}.", now, ALERT_EVERY,
        )
        return None
    db.record_post(conn, mlb_id=cand.mlb_id, niche=niche.name, channel="whatsapp", chat=key,
                   status="sent", sent_at=now, message_id=message_id, price=offer.price)
    if owns_queue:
        db.save_candidate(conn, dataclasses.replace(
            cand, state=S.POSTED, decided_at=now, ref_price=offer.price,
        ))
    _next_jitter(conn, key, pacing, rng)
    return cand.mlb_id
