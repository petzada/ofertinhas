"""ROAS geral: comissão do portal de afiliados ÷ gasto na Meta, por dia.

O Mercado Livre não aceita Pixel nem avisa vendas de afiliado, e o caminho anúncio → grupo →
oferta → compra quebra a atribuição. Então o ROAS é o geral do período: a extensão manda a
comissão de cada dia (`POST /ext/earnings`) e o job `ads_sync` busca o gasto e os leads das
campanhas na API de Marketing da Meta. A comissão inclui todas as vendas do afiliado
(Telegram e WhatsApp), não só as que vieram dos anúncios.

Os dois lados ficam em `settings` por dia (`roas:spend:<data>`, `roas:earn:<data>`).
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from . import db
from .models import TZ

SPEND_KEY = "roas:spend:{day}"  # {"spend": float, "leads": int, "at": iso}
EARN_SYNC_KEY = "roas:earnings_synced_at"
EARN_EVERY = timedelta(hours=3)  # a extensão lê o relatório do portal no máximo a cada 3 h
EARN_DAYS = 8  # cabe numa página do relatório (10 linhas)
DAILY_URL = (
    "https://www.mercadolivre.com.br/affiliate-program/api/dashboard/detalle-diario/general"
    "?metric_tab=general&type=GENERAL&filter_time_range={since}T00:00:00.000-03:00--"
    "{until}T00:00:00.000-03:00"
)
EARN_KEY = "roas:earn:{day}"  # {"commission": float, "orders": int, "clicks": int, "at": iso}
GRAPH = "https://graph.facebook.com/v21.0"
LEAD_ACTIONS = ("offsite_conversion.fb_pixel_lead", "lead")


class MetaAdsError(Exception):
    pass


def parse_insights(data: dict) -> dict[str, dict[str, float]]:
    """Resposta do `/insights` com `time_increment=1` → {data: {spend, leads}}."""
    days: dict[str, dict[str, float]] = {}
    for row in data.get("data", []):
        day = row["date_start"]
        actions = {a["action_type"]: float(a["value"]) for a in row.get("actions", [])}
        leads = next((actions[k] for k in LEAD_ACTIONS if k in actions), 0.0)
        entry = days.setdefault(day, {"spend": 0.0, "leads": 0.0})
        entry["spend"] += float(row.get("spend", 0))
        entry["leads"] += leads
    return days


@dataclass
class MetaAds:
    """Gasto e leads por dia das campanhas cujo nome contém `name_contains`."""

    http: Any  # httpx.AsyncClient
    token: str
    account_id: str  # act_<número>
    name_contains: str = ""

    async def daily(self, since: date, until: date) -> dict[str, dict[str, float]]:
        params = {
            "access_token": self.token,
            "level": "campaign",
            "fields": "spend,actions",
            "time_increment": "1",
            "time_range": f'{{"since":"{since.isoformat()}","until":"{until.isoformat()}"}}',
            "limit": "500",
        }
        if self.name_contains:
            params["filtering"] = (
                f'[{{"field":"campaign.name","operator":"CONTAIN","value":"{self.name_contains}"}}]'
            )
        response = await self.http.get(
            f"{GRAPH}/{self.account_id}/insights", params=params, timeout=30
        )
        data = response.json()
        if response.status_code != 200 or "error" in data:
            message = data.get("error", {}).get("message", response.text[:200])
            raise MetaAdsError(f"Meta {response.status_code}: {message}")
        return parse_insights(data)


async def sync_spend(conn: sqlite3.Connection, meta: MetaAds, now: datetime, days: int = 7) -> int:
    """Grava o gasto dos últimos `days` dias (a Meta ainda ajusta os dias recentes)."""
    today = now.astimezone(TZ).date()
    since = today - timedelta(days=days - 1)
    found = await meta.daily(since, today)
    for offset in range(days):
        day = (since + timedelta(days=offset)).isoformat()
        entry = found.get(day, {"spend": 0.0, "leads": 0.0})
        db.set_setting(
            conn,
            SPEND_KEY.format(day=day),
            {
                "spend": round(entry["spend"], 2),
                "leads": int(entry["leads"]),
                "at": now.isoformat(),
            },
        )
    return len(found)


def earnings_request(conn: sqlite3.Connection, now: datetime) -> dict | None:
    """O relatório diário que a extensão deve ler agora, ou None se a última leitura é recente.
    O intervalo vai de 7 dias atrás até amanhã (exclusivo), no horário de São Paulo."""
    last = db.get_setting(conn, EARN_SYNC_KEY)
    if last and now - datetime.fromisoformat(last) < EARN_EVERY:
        return None
    today = now.astimezone(TZ).date()
    since, until = today - timedelta(days=EARN_DAYS - 1), today + timedelta(days=1)
    return {
        "url": DAILY_URL.format(since=since.isoformat(), until=until.isoformat()),
        "since": since.isoformat(),
        "until": until.isoformat(),
    }


def parse_daily(body: dict, since: date, until: date) -> list[dict]:
    """`detalle-diario` do portal → comissão por dia. Dias sem movimento não vêm no
    relatório e entram com zero, para não ficar um ganho antigo no lugar."""
    rows = {r["date"]: r for r in body.get("item_list", [])}
    if body.get("total_results", len(rows)) > len(rows):
        raise ValueError("relatório com mais de uma página: diminua o intervalo")
    out = []
    day = since
    while day < until:
        row = rows.get(day.isoformat(), {})
        out.append(
            {
                "date": day.isoformat(),
                "commission": float(row.get("earnings", 0)),
                "orders": int(row.get("orders", 0)),
                "clicks": int(row.get("touchpoints", 0)),
            }
        )
        day += timedelta(days=1)
    return out


def save_earnings(conn: sqlite3.Connection, rows: list[dict], now: datetime) -> int:
    """Comissão por dia vinda da extensão: [{"date": "AAAA-MM-DD", "commission": 12.3}]."""
    saved = 0
    for row in rows:
        day = date.fromisoformat(str(row["date"])).isoformat()
        commission = float(row["commission"])
        if commission < 0:
            raise ValueError(f"comissão negativa em {day}")
        db.set_setting(
            conn,
            EARN_KEY.format(day=day),
            {
                "commission": round(commission, 2),
                "orders": int(row.get("orders", 0)),
                "clicks": int(row.get("clicks", 0)),
                "at": now.isoformat(),
            },
        )
        saved += 1
    db.set_setting(conn, EARN_SYNC_KEY, now.isoformat())
    return saved


@dataclass(frozen=True)
class Period:
    spend: float
    leads: int
    commission: float
    orders: int
    has_spend: bool
    has_earnings: bool

    @property
    def cpl(self) -> float | None:
        return self.spend / self.leads if self.leads else None

    @property
    def roas(self) -> float | None:
        return self.commission / self.spend if self.spend and self.has_earnings else None


def period(conn: sqlite3.Connection, last_day: date, days: int) -> Period:
    spend = commission = 0.0
    leads = orders = 0
    has_spend = has_earnings = False
    for offset in range(days):
        day = (last_day - timedelta(days=offset)).isoformat()
        s = db.get_setting(conn, SPEND_KEY.format(day=day))
        e = db.get_setting(conn, EARN_KEY.format(day=day))
        if s:
            has_spend = True
            spend += s["spend"]
            leads += s["leads"]
        if e:
            has_earnings = True
            commission += e["commission"]
            orders += e.get("orders", 0)
    return Period(round(spend, 2), leads, round(commission, 2), orders, has_spend, has_earnings)


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _line(label: str, p: Period) -> str:
    parts = [f"gasto {_brl(p.spend)}", f"leads {p.leads}"]
    if p.cpl is not None:
        parts.append(f"CPL {_brl(p.cpl)}")
    parts.append(
        f"pedidos {p.orders} • comissão {_brl(p.commission)}" if p.has_earnings else "comissão ?"
    )
    if p.roas is not None:
        parts.append(f"ROAS {p.roas:.2f}".replace(".", ","))
    return f"• {label}: " + " • ".join(parts)


def status_lines(conn: sqlite3.Connection, now: datetime) -> list[str]:
    """Bloco do status fixado; vazio enquanto não houver gasto nem comissão gravados."""
    today = now.astimezone(TZ).date()
    week = period(conn, today, 7)
    if not (week.has_spend or week.has_earnings):
        return []
    return [
        "",
        "<b>Meta Ads × comissão</b>",
        _line("hoje", period(conn, today, 1)),
        _line("ontem", period(conn, today - timedelta(days=1), 1)),
        _line("7 dias", week),
    ]
