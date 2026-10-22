import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ofertinhas.collector.parsers import parse_hub_search, parse_sold

FIXTURES = Path(__file__).parents[1] / "fixtures" / "portal"
NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)


def load(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data["request"]["body"], data["response"]["body"]


def by_id(offers):
    return {o.mlb_id: o for o in offers}


def test_general_page_parses_every_card():
    req, resp = load("hub-search-geral-offset18.json")
    offers = parse_hub_search(req, resp, now=NOW)
    assert len(offers) == len(resp["polycard_client_model"]["polycards"]) == 18
    assert all(o.category_path == () for o in offers)  # sem filtro de categoria


def test_card_with_extra_commission():
    o = by_id(parse_hub_search(*load("hub-search-geral-offset18.json"), now=NOW))["MLB7818802816"]
    assert o.title.startswith("Guarda Sol Gigante 2,40m Uv Praia Piscina")
    assert o.commission_pct == 17.0 and o.extra_commission is True
    assert (o.price, o.original_price) == (87.2, 189.9)
    assert o.rating == 4.8 and o.sold_count == 100
    assert o.highlight == "MAIS VENDIDO"
    assert o.item_type == "product"
    assert o.permalink == (
        "https://www.mercadolivre.com.br/guarda-sol-gigante-240m-uv-praia-piscina-camping-"
        "pesca-verao-cor-azul-marinho-vai-de-tech/p/MLB80519717"
    )
    assert o.image_url == (
        "https://http2.mlstatic.com/D_NQ_NP_2X_651621-MLA117648908194_102026-F.webp"
    )
    assert o.pix_only is False and o.international is False
    assert o.collected_at == NOW


def test_card_with_regular_commission_and_user_product():
    o = by_id(parse_hub_search(*load("hub-search-geral-offset18.json"), now=NOW))["MLB4462175099"]
    assert o.commission_pct == 12.0 and o.extra_commission is False
    assert o.item_type == "user_product"
    assert o.permalink.endswith("/up/MLBU3779321624")
    assert o.rating == 4.4 and o.sold_count == 1000


def test_card_without_previous_price():
    o = by_id(parse_hub_search(*load("hub-search-geral-offset18.json"), now=NOW))["MLB4196595477"]
    assert o.original_price is None and o.price == 35.89
    assert o.sold_count == 5000


def test_pix_only_discount_and_missing_review():
    o = by_id(parse_hub_search(*load("hub-search-geral-offset54-pix.json"), now=NOW))[
        "MLB5293771073"
    ]
    assert o.pix_only is True
    assert (o.price, o.original_price) == (3599, 5499)
    assert o.commission_pct == 5.0
    assert o.rating is None and o.sold_count is None


def test_category_comes_from_request_filter():
    offers = parse_hub_search(*load("hub-search-categoria-bebes.json"), now=NOW)
    assert offers and all(o.category_path == ("MLB1384",) for o in offers)


def test_international_card():
    offers = by_id(parse_hub_search(*load("hub-search-categoria-games-internacional.json"),
                                    now=NOW))
    o = offers["MLB5338583985"]
    assert o.international is True and o.category_path == ("MLB1144",)
    assert o.original_price is None


def test_highlight_without_icon_placeholders():
    req, resp = load("hub-search-geral-offset18.json")
    highlights = {o.highlight for o in parse_hub_search(req, resp, now=NOW)}
    assert not any("{" in (h or "") for h in highlights)


def test_unknown_payload_returns_none():
    assert parse_hub_search({}, {"foo": 1}, now=NOW) is None
    assert parse_hub_search({}, None, now=NOW) is None


def test_all_cards_broken_returns_none():
    resp = {"polycard_client_model": {"polycards": [{"metadata": {}}, {"x": 1}]}}
    assert parse_hub_search({}, resp, now=NOW) is None


def test_empty_page_returns_empty_list():
    assert parse_hub_search({}, {"polycard_client_model": {"polycards": []}}, now=NOW) == []


def test_one_broken_card_is_skipped():
    req, resp = load("hub-search-geral-offset18.json")
    resp["polycard_client_model"]["polycards"][0]["components"] = []
    assert len(parse_hub_search(req, resp, now=NOW)) == 17


@pytest.mark.parametrize(
    ("text", "expected"),
    [("| +100 vendidos", 100), ("| +5mil vendidos", 5000), ("| +1000 vendidos", 1000),
     ("| +10mil vendidos", 10000), ("| +1 mi vendidos", 1_000_000), ("| +1.000 vendidos", 1000),
     ("| Novo", None)],
)
def test_parse_sold(text, expected):
    assert parse_sold(text) == expected


def without_commission(resp):
    for card in resp["polycard_client_model"]["polycards"]:
        card["components"] = [c for c in card["components"]
                              if c["id"] != "affiliates_commission_chip"]
        card["metadata"]["brand_commission"] = card["metadata"]["extra_commission"] = "none"
    return resp


def test_page_of_products_without_commission_is_valid_but_empty():
    req, resp = load("hub-search-categoria-bebes.json")
    assert parse_hub_search(req, without_commission(resp), now=NOW) == []


def test_cards_without_commission_are_skipped_among_good_ones():
    req, resp = load("hub-search-geral-offset18.json")
    cards = resp["polycard_client_model"]["polycards"]
    without_commission({"polycard_client_model": {"polycards": cards[:5]}})
    assert len(parse_hub_search(req, resp, now=NOW)) == len(cards) - 5
