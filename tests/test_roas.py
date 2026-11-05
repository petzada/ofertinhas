"""ROAS geral: gasto e leads da Meta por dia + comissão do portal, no status fixado."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from ofertinhas import db
from ofertinhas.config import ConfigError, load_config_text
from ofertinhas.roas import (
    MetaAds,
    MetaAdsError,
    earnings_request,
    parse_daily,
    period,
    save_earnings,
    status_lines,
    sync_spend,
)

NOW = datetime(2026, 11, 7, 15, 0, tzinfo=UTC)  # 12h em São Paulo
INSIGHTS = {
    "data": [
        {
            "date_start": "2026-11-06",
            "spend": "18.50",
            "actions": [
                {"action_type": "offsite_conversion.fb_pixel_lead", "value": "7"},
                {"action_type": "link_click", "value": "30"},
            ],
        },
        {
            "date_start": "2026-11-07",
            "spend": "9.00",
            "actions": [{"action_type": "offsite_conversion.fb_pixel_lead", "value": "3"}],
        },
        {"date_start": "2026-11-07", "spend": "1.00"},  # outra campanha, sem lead
    ]
}


def meta(handler) -> MetaAds:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MetaAds(http, "tok", "act_1", "Thai | Grupo VIP")


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.migrate(c)
    return c


async def test_sync_spend_sums_campaigns_per_day_and_filters_by_name(conn):
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json=INSIGHTS)

    await sync_spend(conn, meta(handler), NOW, days=3)
    assert "Thai | Grupo VIP" in seen["filtering"] and seen["time_increment"] == "1"
    assert '"since":"2026-11-05"' in seen["time_range"]
    today = period(conn, NOW.date(), 1)
    assert (today.spend, today.leads) == (10.0, 3)
    assert period(conn, NOW.date(), 3).spend == 28.5  # 05/11 sem gasto vira 0


async def test_meta_error_is_raised(conn):
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "token expirado"}})

    with pytest.raises(MetaAdsError, match="token expirado"):
        await sync_spend(conn, meta(handler), NOW)


async def test_status_shows_cpl_commission_and_roas(conn):
    await sync_spend(conn, meta(lambda r: httpx.Response(200, json=INSIGHTS)), NOW, days=2)
    save_earnings(conn, [{"date": "2026-11-06", "commission": 37, "orders": 2}], NOW)
    text = "\n".join(status_lines(conn, NOW))
    assert (
        "ontem: gasto R$ 18,50 • leads 7 • CPL R$ 2,64 • pedidos 2 • comissão R$ 37,00 • ROAS 2,00"
    ) in text
    assert "hoje: gasto R$ 10,00 • leads 3 • CPL R$ 3,33 • comissão ?" in text
    assert "7 dias: gasto R$ 28,50 • leads 10" in text


def test_no_data_no_block(conn):
    assert status_lines(conn, NOW) == []


def test_negative_commission_rejected(conn):
    with pytest.raises(ValueError):
        save_earnings(conn, [{"date": "2026-11-06", "commission": -1}], NOW)


def test_ads_config_needs_act_prefix():
    base = "niches: {casa: {categories: [MLB1574], telegram_chat_id: -1}}\n"
    assert load_config_text(base + "ads: {meta_account_id: act_123}").ads.meta_account_id
    with pytest.raises(ConfigError):
        load_config_text(base + "ads: {meta_account_id: '123'}")


# formato real do portal (05/11/2026), com dias sem movimento omitidos
DAILY = {
    "item_list": [
        {
            "date": "2026-11-02",
            "quantity": 1,
            "orders": 1,
            "earnings": 4.5,
            "cvr": 0,
            "touchpoints": 3,
            "coupons": 0,
        },
        {
            "date": "2026-11-05",
            "quantity": 0,
            "orders": 0,
            "earnings": 0,
            "cvr": 0,
            "touchpoints": 2,
            "coupons": 0,
        },
    ],
    "page": 1,
    "items_per_page": 10,
    "total_results": 2,
}


def test_parse_daily_fills_missing_days_with_zero():
    rows = parse_daily(DAILY, date(2026, 11, 1), date(2026, 11, 6))
    assert [r["date"] for r in rows] == [f"2026-11-0{d}" for d in range(1, 6)]
    assert rows[1] == {"date": "2026-11-02", "commission": 4.5, "orders": 1, "clicks": 3}
    assert rows[0]["commission"] == 0


def test_parse_daily_refuses_partial_report():
    with pytest.raises(ValueError):
        parse_daily({**DAILY, "total_results": 12}, date(2026, 11, 1), date(2026, 11, 6))


def test_earnings_request_every_3_hours(conn):
    req = earnings_request(conn, NOW)
    assert req["since"] == "2026-10-31" and req["until"] == "2026-11-08"
    assert "detalle-diario" in req["url"] and "2026-10-31T00:00:00.000-03:00--" in req["url"]
    save_earnings(conn, parse_daily(DAILY, date(2026, 10, 31), date(2026, 11, 8)), NOW)
    assert earnings_request(conn, NOW + timedelta(hours=2)) is None
    assert earnings_request(conn, NOW + timedelta(hours=3)) is not None
