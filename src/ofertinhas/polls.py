"""Enquete semanal nos grupos de WhatsApp: uma pergunta do `BANK` por semana, em rodízio.

O nicho liga com `polls: {weekday: qua, at: "19:30"}` no config. A enquete sai no dia e
horário marcados (até `SEND_WINDOW` depois, se o sistema estava fora na hora), uma vez por
semana e por grupo. Antes de cada nova, o admin recebe no Telegram o resultado da anterior.

Os votos chegam pelo webhook da WhatsMiau (rota `/wa/` da nuvem). Ela não documenta o formato
do voto, então `record_vote` aceita o nome da opção ou o SHA-256 dele (é assim que o WhatsApp
guarda o voto) e guarda em `wa:unparsed` os eventos de enquete que não entender, para ajustar.
Quem votou é gravado só como hash do número.
"""

import base64
import hashlib
import json
import sqlite3
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from . import db
from .config import WEEKDAYS, AppConfig
from .models import TZ
from .pipeline import niche_configs

SEND_WINDOW = timedelta(hours=2)
UNPARSED_KEY = "wa:unparsed"
UNPARSED_KEEP = 5
UNPARSED_MAX_CHARS = 4000


@dataclass(frozen=True)
class Poll:
    key: str  # identifica a pergunta no rodízio; trocar o texto mantém o histórico
    question: str
    options: tuple[str, ...]  # 2 a 12
    multi: bool = False


BANK: dict[str, tuple[Poll, ...]] = {
    "noivas": (
        Poll("data", "💍 Quando é o grande dia?", (
            "Ainda em 2026", "1º semestre de 2027", "2º semestre de 2027", "2028 ou depois",
            "Ainda sem data", "Já casei 🥂")),
        Poll("achados", "🛍️ Quais achadinhos você mais quer ver aqui?", (
            "Cozinha e chá de panela", "Cama, mesa e banho", "Eletro da lista de presentes",
            "Beleza e skincare da noiva", "Decoração e lembrancinhas", "Lua de mel e viagem",
            "Móveis e casa nova"), multi=True),
        Poll("fase", "📋 Em que fase do planejamento você está?", (
            "Acabei de ficar noiva", "Escolhendo local e fornecedores",
            "Lista de presentes e chá", "Reta final (menos de 3 meses)", "Já casei")),
        Poll("lista", "🎁 Como vai ser sua lista de presentes?", (
            "Presentes físicos em loja", "Em dinheiro / PIX no site do casamento",
            "As duas", "Ainda não decidi")),
        Poll("convidados", "👥 Quantos convidados vocês esperam?", (
            "Mini wedding (até 50)", "50 a 120", "120 a 250", "Mais de 250",
            "Só no civil / cerimônia íntima")),
        Poll("cha", "🫖 Vai ter chá antes do casamento?", (
            "Chá de panela", "Chá bar com o noivo", "Chá de lingerie", "Chá de casa nova",
            "Não vou fazer", "Ainda não sei")),
        Poll("preco", "💸 Que faixa de preço você mais compra nos achadinhos?", (
            "Até R$ 50", "R$ 50 a R$ 150", "R$ 150 a R$ 400", "Acima de R$ 400")),
        Poll("site", "💻 Vocês vão ter site do casamento (RSVP, lista, informações)?", (
            "Já temos", "Queremos fazer", "Nem tinha pensado nisso", "Não vamos ter")),
        Poll("casa", "🏡 Como está a casa nova?", (
            "Já moramos juntos, casa montada", "Já moramos juntos, falta muita coisa",
            "Vamos montar do zero", "Vamos morar com a família por um tempo")),
        Poll("orcamento", "💰 Qual o orçamento total do casamento?", (
            "Até R$ 15 mil", "R$ 15 a 40 mil", "R$ 40 a 80 mil", "Mais de R$ 80 mil",
            "Prefiro não dizer")),
        Poll("estilo", "✨ Qual o estilo do seu casamento?", (
            "Clássico", "Rústico / campo", "Praia", "Boho", "Minimalista", "Moderno")),
        Poll("lua_de_mel", "✈️ Lua de mel: pra onde?", (
            "Nordeste", "Serra / Sul", "Praia no exterior", "Cidade no exterior",
            "Ainda não sei", "Sem lua de mel por enquanto")),
        Poll("dor", "😮‍💨 O que mais tira seu sono no planejamento?", (
            "Orçamento", "Lista de convidados", "Escolher fornecedores", "Organizar tudo",
            "Família palpitando 😅")),
        Poll("horario", "⏰ Em que horário você mais vê as ofertas do grupo?", (
            "Manhã", "Almoço", "Fim da tarde", "Noite")),
        Poll("black_friday", "🖤 Na Black Friday, o que você vai caçar?", (
            "Eletrodomésticos", "Panelas e cozinha", "Cama e banho", "Beleza", "Móveis",
            "Malas e viagem"), multi=True),
        Poll("conteudo", "💡 O que mais te ajudaria aqui no grupo?", (
            "Mais ofertas", "Checklists e planilhas", "Dicas de fornecedores",
            "Ideias de decoração DIY", "Ofertas para a lua de mel"), multi=True),
    ),
}


def next_poll(bank: tuple[Poll, ...], history: list[str]) -> Poll:
    """A que nunca saiu (na ordem do banco) ou a que saiu há mais tempo."""
    last_sent = {key: i for i, key in enumerate(history)}
    return min(bank, key=lambda p: last_sent.get(p.key, -1))


def week_of(now: datetime) -> str:
    return now.astimezone(TZ).strftime("%G-W%V")


def voter_id(jid: str) -> str:
    return hashlib.sha256(jid.encode()).hexdigest()[:16]


def results(conn: sqlite3.Connection, poll: dict) -> dict[str, Any]:
    votes = db.poll_votes(conn, poll["message_id"])
    counts = Counter(option for vote in votes for option in vote)
    return {"question": poll["question"], "sent_at": poll["sent_at"],
            "voters": sum(1 for vote in votes if vote),
            "counts": {option: counts[option] for option in poll["options"]}}


def results_text(result: dict[str, Any]) -> str:
    lines = [f"📊 Resultado da enquete: {result['question']}",
             f"{result['voters']} pessoa(s) votaram"]
    total = max(result["voters"], 1)
    for option, n in sorted(result["counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"• {option}: {n} ({n * 100 // total}%)")
    return "\n".join(lines)


async def send_weekly_polls(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    whatsapp,
    now: datetime,
    notify: Callable[[str], Awaitable[None]],
    *,
    dry_run: bool,
    test_jid: str | None = None,
    force_niche: str | None = None,
) -> list[str]:
    """Manda a enquete da semana de cada nicho que tiver `polls`. Em `dry_run`, vai só para
    `test_jid`. `force_niche` manda já a próxima daquele nicho, fora do dia e do horário."""
    if not cfg.whatsapp_enabled or whatsapp is None:
        return []
    local = now.astimezone(TZ)
    week = week_of(now)
    sent = []
    for name, niche in niche_configs(conn, cfg).items():
        bank = BANK.get(name)
        if force_niche is not None and name != force_niche:
            continue
        if not (niche.polls and bank) or (niche.paused and force_niche is None):
            continue
        target = test_jid if dry_run else niche.whatsapp_group_jid
        if not target:
            continue
        if force_niche is None:
            start = datetime.combine(local.date(), niche.polls.at, tzinfo=TZ)
            if WEEKDAYS[local.weekday()] != niche.polls.weekday \
                    or not start <= local < start + SEND_WINDOW \
                    or db.poll_sent(conn, name, target, week):
                continue
        previous = db.recent_polls(conn, 1, name)
        if previous:
            await notify(results_text(results(conn, previous[0])))
        poll = next_poll(bank, db.poll_history(conn, name))
        message_id = await whatsapp.send_poll(target, poll.question, list(poll.options),
                                              poll.multi)
        db.record_poll(conn, message_id=message_id or f"sem-id-{name}-{now.isoformat()}",
                       niche=name, poll_key=poll.key, chat=target, week=week,
                       question=poll.question, options=list(poll.options), sent_at=now)
        sent.append(f"{name}:{poll.key}")
    return sent


# --- votos (webhook da WhatsMiau) ------------------------------------------


def _find(node: Any, key: str) -> Any:
    """Primeiro valor de `key` em dicts e listas aninhados (busca em largura)."""
    queue = [node]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            if key in current:
                return current[key]
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)
    return None


def _option_names(selected: list, options: list[str]) -> list[str] | None:
    """Converte a escolha em nomes de opção. O WhatsApp guarda o SHA-256 do nome (em hex ou
    base64, conforme a API); `None` se algum item não bater com nenhuma opção."""
    lookup = {}
    for option in options:
        digest = hashlib.sha256(option.encode()).digest()
        for form in (option, digest.hex(), digest.hex().upper(),
                     base64.b64encode(digest).decode()):
            lookup[form] = option
    names = []
    for item in selected:
        if isinstance(item, dict):
            item = item.get("name") or item.get("optionName")
        name = lookup.get(item) if isinstance(item, str) else None
        if name is None:
            return None
        names.append(name)
    return names


def _voter(data: Any) -> str | None:
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(key, dict):
        return None
    jid = key.get("participantAlt") or key.get("participant") or key.get("remoteJid")
    return jid if isinstance(jid, str) and not jid.endswith("@g.us") else None


def _keep_unparsed(conn: sqlite3.Connection, event: dict, why: str, now: datetime) -> None:
    kept = db.get_setting(conn, UNPARSED_KEY, default=[])
    raw = json.dumps(event, ensure_ascii=False)[:UNPARSED_MAX_CHARS]
    db.set_setting(conn, UNPARSED_KEY,
                   [*kept, {"at": now.isoformat(), "why": why, "event": raw}][-UNPARSED_KEEP:])


def record_vote(conn: sqlite3.Connection, event: dict, now: datetime) -> str:
    """Trata um evento do webhook. Devolve `voto`, `ignorado` (não é voto de enquete nossa) ou
    `não entendi` (guardado em `wa:unparsed`)."""
    data = event.get("data") if isinstance(event, dict) else None
    if data is None:
        return "ignorado"
    aggregate = _find(data, "pollUpdates")
    if isinstance(aggregate, list) and aggregate:
        return _record_aggregate(conn, event, data, aggregate, now)
    creation = _find(data, "pollCreationMessageKey")
    if not isinstance(creation, dict):
        return "ignorado"
    poll = db.get_poll(conn, str(creation.get("id", "")))
    if poll is None:
        return "ignorado"
    voter = _voter(data)
    selected = _find(data, "selectedOptions")
    names = _option_names(selected, poll["options"]) if isinstance(selected, list) else None
    if voter is None or names is None:
        _keep_unparsed(conn, event, "voto sem quem votou ou opção desconhecida", now)
        return "não entendi"
    db.set_poll_vote(conn, poll["message_id"], voter_id(voter), names, now)
    return "voto"


def _record_aggregate(conn, event, data, aggregate: list, now: datetime) -> str:
    """Formato da Evolution API: `pollUpdates: [{name, voters: [jid...]}]` com o placar todo
    da enquete; regrava o voto de cada pessoa listada."""
    key = data.get("key") if isinstance(data, dict) else None
    message_id = (key or {}).get("id") or data.get("keyId") or data.get("messageId")
    poll = db.get_poll(conn, str(message_id or ""))
    if poll is None:
        return "ignorado"
    by_voter: dict[str, list[str]] = {}
    for entry in aggregate:
        names = _option_names([entry], poll["options"]) if isinstance(entry, dict) else None
        if names is None:
            _keep_unparsed(conn, event, "placar com opção desconhecida", now)
            return "não entendi"
        for jid in entry.get("voters") or []:
            by_voter.setdefault(jid, []).extend(names)
    for jid, names in by_voter.items():
        db.set_poll_vote(conn, poll["message_id"], voter_id(jid), names, now)
    return "voto"
