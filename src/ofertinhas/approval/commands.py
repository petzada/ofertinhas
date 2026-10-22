"""Comandos do admin no bot. Cada um recebe os argumentos e devolve a resposta em HTML."""

import html
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from .. import db
from ..config import AppConfig, ConfigError, Weights, deep_merge
from ..models import CandidateState
from . import actions

S = CandidateState
HELP = """<b>Comandos</b>
/fila [nicho] — pendentes e fila de postagem
/top &lt;nicho&gt; — aprova agora a melhor pendente
/corte &lt;nicho&gt; &lt;auto&gt; &lt;manual&gt; — notas de corte
/peso &lt;nicho&gt; &lt;critério&gt; &lt;valor&gt; — peso de um critério
/pausar [nicho|coleta] — pausa disparos (todos, um nicho) ou a extensão
/retomar [nicho|coleta] — retoma
/stats — posts de hoje
/chatid — id deste chat"""


@dataclass
class CommandContext:
    conn: sqlite3.Connection
    cfg: AppConfig
    now: datetime
    chat_id: int


class _Usage(Exception):
    pass


def _niche(ctx: CommandContext, name: str) -> str:
    if name not in ctx.cfg.niches:
        raise _Usage(f"nicho desconhecido: {html.escape(name)} "
                     f"(existem: {', '.join(ctx.cfg.niche_names())})")
    return name


def _number(text: str) -> float:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise _Usage(f"não é um número: {html.escape(text)}") from None


def _set_overrides(ctx: CommandContext, niche: str, changes: dict) -> None:
    """Valida o resultado inteiro antes de gravar qualquer coisa."""
    merged = deep_merge(db.niche_overrides(ctx.conn, niche), changes)
    try:
        ctx.cfg.for_niche(niche, merged)
    except ConfigError as e:
        raise _Usage(html.escape(str(e))) from None
    db.set_setting(ctx.conn, f"override:{niche}", merged)


def _cmd_chatid(ctx: CommandContext, args: list[str]) -> str:
    return f"ID deste chat: <code>{ctx.chat_id}</code>"


def _cmd_corte(ctx: CommandContext, args: list[str]) -> str:
    if len(args) != 3:
        raise _Usage("uso: /corte &lt;nicho&gt; &lt;auto&gt; &lt;manual&gt;")
    niche = _niche(ctx, args[0])
    auto, manual = _number(args[1]), _number(args[2])
    _set_overrides(ctx, niche, {"auto_approve_at": auto, "manual_review_at": manual})
    return (
        f"Corte de <b>{niche}</b>: aprova sozinho a partir de {auto:g}, "
        f"revisão a partir de {manual:g}."
    )


def _cmd_peso(ctx: CommandContext, args: list[str]) -> str:
    if len(args) != 3:
        raise _Usage("uso: /peso &lt;nicho&gt; &lt;critério&gt; &lt;valor&gt;")
    niche = _niche(ctx, args[0])
    criterion = args[1]
    if criterion not in Weights.model_fields:
        raise _Usage(f"critério desconhecido: {html.escape(criterion)} "
                     f"(existem: {', '.join(Weights.model_fields)})")
    value = _number(args[2])
    _set_overrides(ctx, niche, {"weights": {criterion: value}})
    return f"Peso de <b>{criterion}</b> em <b>{niche}</b>: {value:g}."


def _pause_targets(ctx: CommandContext, args: list[str]) -> list[str] | None:
    """Nichos afetados; None quando o alvo é a coleta da extensão."""
    if not args:
        return ctx.cfg.niche_names()
    if args[0] == "coleta":
        return None
    return [_niche(ctx, args[0])]


def _cmd_pausar(ctx: CommandContext, args: list[str]) -> str:
    targets = _pause_targets(ctx, args)
    if targets is None:
        db.set_setting(ctx.conn, db.EXTENSION_PAUSED_KEY,
                       {"reason": "manual", "url": None, "at": ctx.now.isoformat()})
        return "⏸️ Coleta e geração de links pausadas. Use /retomar coleta para voltar."
    for niche in targets:
        db.set_niche_override(ctx.conn, niche, "paused", True)
    return f"⏸️ Disparos pausados: {', '.join(targets)}."


def _cmd_retomar(ctx: CommandContext, args: list[str]) -> str:
    targets = _pause_targets(ctx, args)
    if targets is None:
        db.set_setting(ctx.conn, db.EXTENSION_PAUSED_KEY, None)
        return "▶️ Coleta e geração de links retomadas."
    for niche in targets:
        db.set_niche_override(ctx.conn, niche, "paused", False)
    return f"▶️ Disparos retomados: {', '.join(targets)}."


def _cmd_fila(ctx: CommandContext, args: list[str]) -> str:
    niches = [_niche(ctx, args[0])] if args else ctx.cfg.niche_names()
    blocks = []
    for niche in niches:
        counts = db.count_candidates(ctx.conn, niche)
        waiting = counts.get(S.RENDERED, 0) + counts.get(S.QUEUED, 0)
        lines = [
            f"<b>{niche}</b> — pendentes: {counts.get(S.PENDING, 0)} • "
            f"aprovadas: {counts.get(S.APPROVED, 0)} • com link: {counts.get(S.LINKED, 0)} • "
            f"prontas para postar: {waiting}"
        ]
        for cand in db.candidates_by_state(ctx.conn, S.PENDING, niche=niche)[:5]:
            offer = db.get_offer(ctx.conn, cand.mlb_id)
            lines.append(f"  {cand.score:.0f} • {cand.mlb_id} • {html.escape(offer.title[:50])}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _cmd_top(ctx: CommandContext, args: list[str]) -> str:
    if len(args) != 1:
        raise _Usage("uso: /top &lt;nicho&gt;")
    niche = _niche(ctx, args[0])
    cand = actions.force_top(ctx.conn, niche, ctx.now)
    if cand is None:
        return f"Nenhuma oferta pendente em {niche}."
    return f"✅ {cand.mlb_id} (nota {cand.score:.0f}) aprovada em {niche}."


def _cmd_stats(ctx: CommandContext, args: list[str]) -> str:
    rows = db.posts_today_summary(ctx.conn, ctx.now)
    if not rows:
        return "Nenhum post enviado hoje."
    by_niche: dict[str, list[str]] = {}
    for niche, channel, n in rows:
        by_niche.setdefault(niche, []).append(f"{channel}: {n}")
    return "<b>Posts de hoje</b>\n" + "\n".join(
        f"{niche} — {', '.join(parts)}" for niche, parts in by_niche.items()
    )


COMMANDS: dict[str, Callable[[CommandContext, list[str]], str]] = {
    "chatid": _cmd_chatid,
    "corte": _cmd_corte,
    "peso": _cmd_peso,
    "pausar": _cmd_pausar,
    "retomar": _cmd_retomar,
    "fila": _cmd_fila,
    "top": _cmd_top,
    "stats": _cmd_stats,
}


def run_command(name: str, args: list[str], ctx: CommandContext) -> str:
    handler = COMMANDS.get(name)
    if handler is None:
        return HELP
    try:
        return handler(ctx, args)
    except _Usage as e:
        return f"⚠️ {e}"
