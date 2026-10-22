"""Link fixo dos grupos de WhatsApp (`/g/<nicho>`): redireciona ao convite do grupo ativo.

Cada nicho tem uma lista ordenada de grupos no setting `groups:<nicho>`. O ativo é o primeiro
que não está lotado; se todos lotarem, segue o último (melhor que um link quebrado) e o admin
é avisado. Os links publicados na bio, nos Pins e nos anúncios nunca mudam: muda só a lista.

A lotação vem da WhatsMiau (`members_job`, a cada 15 min, para os grupos com `jid`) ou da
troca manual pelo admin. Os cliques são contados por nicho, dia (horário de SP), origem
(`utm_source`) e campanha (`utm_campaign`); nada mais da requisição é guardado.
"""

import re
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from .. import db
from ..alerts import notify_throttled
from ..models import TZ

GROUPS_KEY = "groups:{niche}"
# O WhatsApp aceita 1.024 membros; com a checagem de 15 em 15 min, o grupo vira "lotado" um
# pouco antes, para ninguém cair num convite que não entra mais. Lotado não volta sozinho a
# livre se gente sair: o admin desmarca (`full: false`) se quiser.
FULL_AT = 1000
FULL_ALERT_EVERY = timedelta(hours=12)
NICHE = re.compile(r"[a-z0-9_-]{1,40}")
INVITE = re.compile(r"https://chat\.whatsapp\.com/[A-Za-z0-9]{10,40}")
UTM_VALUE = re.compile(r"[a-z0-9_.-]{1,40}")
LONG_NUMBER = re.compile(r"\d{8,}")  # telefone, CPF: não é origem de campanha
NO_SOURCE = "direto"
OTHER = "outro"
# Robôs que abrem o link para montar a pré-visualização (no Pin, na conversa, no post). Os
# navegadores internos dos apps (Instagram, TikTok, Pinterest, Facebook) são gente e contam.
PREVIEW_BOTS = re.compile(
    r"facebookexternalhit|facebot|whatsapp/|pinterestbot|pinterest\.com/bot|telegrambot|"
    r"twitterbot|slackbot|discordbot|linkedinbot|googlebot|bingbot|bytespider|tiktokspider",
    re.I)


def counts_as_click(method: str, user_agent: str | None) -> bool:
    """Só GET de gente: HEAD e os robôs de pré-visualização recebem o 302 sem contar."""
    return method == "GET" and not PREVIEW_BOTS.search(user_agent or "")


def clean_utm(value: str | None, default: str) -> str:
    """Origem ou campanha só com letras, números e `_.-`; qualquer outra coisa vira `outro`,
    para não guardar texto livre (e com ele dado pessoal) vindo da URL."""
    value = (value or "").strip().lower()
    if not value:
        return default
    if not UTM_VALUE.fullmatch(value) or LONG_NUMBER.search(value):
        return OTHER
    return value


def get_groups(conn: sqlite3.Connection, niche: str) -> list[dict[str, Any]]:
    return db.get_setting(conn, GROUPS_KEY.format(niche=niche), default=[])


def all_groups(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    prefix = GROUPS_KEY.format(niche="")
    rows = conn.execute("SELECT key FROM settings WHERE key LIKE ? ORDER BY key",
                        (f"{prefix}%",)).fetchall()
    return {r["key"][len(prefix):]: get_groups(conn, r["key"][len(prefix):]) for r in rows}


def set_groups(conn: sqlite3.Connection, niche: str, links: list[dict[str, Any]]) -> list[dict]:
    """Troca a lista do nicho. Cada item tem `invite` e, opcional, `jid` (para a contagem de
    membros) e `full` (lotado à mão). Membros já contados de um convite que continua na lista
    são mantidos."""
    if not NICHE.fullmatch(niche):
        raise ValueError(f"nicho inválido: {niche!r}")
    before = {g["invite"]: g for g in get_groups(conn, niche)}
    groups = []
    for item in links:
        invite = str(item.get("invite") or "").strip()
        if not INVITE.fullmatch(invite):
            raise ValueError(f"convite inválido: {invite!r} (use https://chat.whatsapp.com/...)")
        jid = item.get("jid") or None
        if jid is not None and not str(jid).endswith("@g.us"):
            raise ValueError(f"jid inválido: {jid!r}")
        old = before.get(invite, {})
        groups.append({"invite": invite, "jid": jid,
                       "full": bool(item.get("full", old.get("full", False))),
                       "members": old.get("members"), "checked_at": old.get("checked_at")})
    if len({g["invite"] for g in groups}) != len(groups):
        raise ValueError("convite repetido na lista")
    db.set_setting(conn, GROUPS_KEY.format(niche=niche), groups)
    return groups


def active_index(groups: list[dict[str, Any]]) -> int | None:
    if not groups:
        return None
    return next((i for i, g in enumerate(groups) if not g.get("full")), len(groups) - 1)


def mark_full(conn: sqlite3.Connection, niche: str) -> list[dict[str, Any]]:
    """Troca manual: o grupo ativo vira lotado e o próximo da lista assume."""
    groups = get_groups(conn, niche)
    index = active_index(groups)
    if index is not None:
        groups[index]["full"] = True
        db.set_setting(conn, GROUPS_KEY.format(niche=niche), groups)
    return groups


def record_click(conn: sqlite3.Connection, niche: str, source: str, campaign: str,
                 now: datetime) -> None:
    day = now.astimezone(TZ).date().isoformat()
    with conn:
        conn.execute(
            "INSERT INTO group_clicks (niche, day, source, campaign, clicks) "
            "VALUES (?, ?, ?, ?, 1) ON CONFLICT (niche, day, source, campaign) "
            "DO UPDATE SET clicks = clicks + 1",
            (niche, day, source, campaign),
        )


def clicks_report(conn: sqlite3.Connection, since_day: str,
                  niche: str | None = None) -> dict[str, list[dict]]:
    where, params = "day >= ?", [since_day]
    if niche:
        where += " AND niche = ?"
        params.append(niche)

    def rows(sql: str) -> list[dict]:
        return [dict(zip(r.keys(), r, strict=True)) for r in conn.execute(sql, params)]

    return {
        "by_day": rows(f"SELECT niche, day, source, campaign, clicks FROM group_clicks "
                       f"WHERE {where} ORDER BY day DESC, niche, clicks DESC, source"),
        "by_source": rows(f"SELECT niche, source, SUM(clicks) AS clicks FROM group_clicks "
                          f"WHERE {where} GROUP BY niche, source ORDER BY niche, clicks DESC"),
    }


def _member_count(group: dict[str, Any]) -> int | None:
    participants = group.get("participants")
    if isinstance(participants, list):
        return len(participants)
    size = group.get("size")
    return size if isinstance(size, int) else None


async def refresh_members(
    conn: sqlite3.Connection,
    fetch_groups: Callable[[], Awaitable[list[dict]]],
    notify: Callable[[str], Awaitable[None]],
    now: datetime,
    full_at: int = FULL_AT,
) -> dict[str, int]:
    """Atualiza os membros dos grupos com `jid` e marca lotado quem chegou a `full_at`. Avisa
    o admin quando o ativo muda e quando não sobra grupo livre. Devolve os membros por jid."""
    lists = {n: g for n, g in all_groups(conn).items() if any(x.get("jid") for x in g)}
    if not lists:
        return {}
    counts = {g.get("id"): _member_count(g) for g in await fetch_groups() or []}
    seen = {}
    for niche, groups in lists.items():
        before = active_index(groups)
        for group in groups:
            members = counts.get(group.get("jid"))
            if members is None:
                continue
            seen[group["jid"]] = members
            group["members"], group["checked_at"] = members, now.isoformat()
            if members >= full_at:
                group["full"] = True
        db.set_setting(conn, GROUPS_KEY.format(niche=niche), groups)
        after = active_index(groups)
        if after != before:
            await notify(f"Grupo do nicho {niche} lotou: o link /g/{niche} agora leva ao "
                         f"grupo {after + 1} de {len(groups)}.")
        if all(g.get("full") for g in groups):
            await notify_throttled(
                conn, notify, f"groups_full:{niche}",
                f"Todos os grupos do nicho {niche} estão lotados: o /g/{niche} segue no último. "
                "Cadastre um convite novo em /admin/groups.", now, FULL_ALERT_EVERY)
    return seen
