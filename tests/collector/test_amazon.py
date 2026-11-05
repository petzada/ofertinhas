"""Ofertas do Dia da Amazon: resposta real (05/11/2026) → Offer com link da tag."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ofertinhas.collector.amazon import collect_requests, parse_deals
from ofertinhas.config import AmazonSource
from ofertinhas.sources import AMAZON, source_of

ROOT = Path(__file__).parents[2]
BODY = json.loads((ROOT / "tests/fixtures/amazon/deals.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 5, 15, tzinfo=UTC)
SRC = AmazonSource(tag="ofertaderainh-20", commission_pct={"MLB1246": 10})


def test_parse_keeps_available_deals_with_list_price():
    offers = parse_deals(BODY, SRC, now=NOW)
    assert [o.mlb_id for o in offers] == [
        "AMZ-B0DC74428B",
        "AMZ-B081DK3VZ8",
    ]  # sem "de" e esgotada saem
    dove, ar = offers
    assert source_of(dove.mlb_id) == AMAZON
    assert dove.affiliate_link == "https://www.amazon.com.br/dp/B0DC74428B?tag=ofertaderainh-20"
    assert (dove.price, dove.original_price, dove.discount_pct) == (26.91, 42.34, 36)
    assert dove.category_path == ("MLB1246",) and dove.commission_pct == 10
    assert dove.rating == 4.8 and dove.sold_count == 7975
    assert dove.image_url == "https://m.media-amazon.com/images/I/61k0+bqK+LL.jpg"
    assert ar.category_path == ("MLB1574",) and ar.commission_pct == 4  # padrão
    assert ar.highlight == "OFERTA RELÂMPAGO"


def test_requested_department_wins_for_category():
    offers = parse_deals(BODY, SRC, department="16522083011", now=NOW)
    assert offers[0].category_path == ("MLB5726",)


def test_requests_follow_niche_categories_and_pages():
    reqs = collect_requests(SRC, ["MLB1246", "MLB5726"])
    assert [r["department"] for r in reqs] == [
        "16194415011",
        "16194415011",
        "16522083011",
        "16522083011",
    ]
    q = parse_qs(urlparse(reqs[1]["url"]).query)
    assert q["startIndex"] == ["30"] and q["pageSize"] == ["30"]
    assert json.loads(q["filters"][0])["includedDepartments"] == ["16194415011"]
