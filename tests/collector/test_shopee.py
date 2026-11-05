"""Shopee Open API: assinatura, consulta e conversão dos nós em ofertas com link pronto."""

import hashlib
import json

import httpx
import pytest

from ofertinhas.collector.shopee import ShopeeClient, ShopeeError, collect, parse_nodes
from ofertinhas.config import ShopeeSearch, ShopeeSource

NODE = {
    "itemId": 22334455,
    "productName": "Paleta de Sombras 18 Cores",
    "commissionRate": "0.08",
    "priceMin": "29.90",
    "priceMax": "39.90",
    "priceDiscountRate": 40,
    "sales": 1520,
    "ratingStar": "4.8",
    "imageUrl": "https://cf.shopee.com.br/file/x",
    "offerLink": "https://s.shopee.com.br/abc",
    "productLink": "https://shopee.com.br/p",
    "shopName": "Loja",
}
SEARCH = ShopeeSearch(keyword="maquiagem", category="MLB1246")


def client(handler, seen=None):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ShopeeClient(http, "123", "segredo", clock=lambda: 1700000000)


def test_parse_node():
    (offer,) = parse_nodes([NODE, {"itemId": 1, "priceMin": "10"}], SEARCH)  # sem link: fora
    assert offer.mlb_id == "SHP-22334455" and offer.affiliate_link == "https://s.shopee.com.br/abc"
    assert (offer.price, offer.original_price, offer.discount_pct) == (29.9, 49.84, 40)
    assert offer.commission_pct == 8 and offer.category_path == ("MLB1246",)
    assert offer.sold_count == 1520 and offer.rating == 4.8


async def test_request_is_signed_over_the_exact_body():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"data": {"productOfferV2": {"nodes": [NODE]}}})

    offers = await collect(client(handler), ShopeeSource(searches=[SEARCH, SEARCH]))
    assert [o.mlb_id for o in offers] == ["SHP-22334455"]  # repetida entre buscas: uma vez
    sig = hashlib.sha256(f"1231700000000{seen['body']}segredo".encode()).hexdigest()
    assert seen["auth"] == f"SHA256 Credential=123, Timestamp=1700000000, Signature={sig}"
    assert json.loads(seen["body"])["variables"]["keyword"] == "maquiagem"


async def test_graphql_error_raises():
    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": "Invalid Signature"}]})

    with pytest.raises(ShopeeError, match="Invalid Signature"):
        await client(handler).offers("x", 10)


def test_unknown_category_rejected():
    with pytest.raises(ValueError):
        ShopeeSource(searches=[ShopeeSearch(keyword="x", category="MLB999")])
