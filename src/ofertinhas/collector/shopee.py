"""Shopee: Open API de afiliados (GraphQL), coletada na nuvem pelo job `shopee_collect`.

Cada busca de `sources.shopee.searches` chama `productOfferV2` com a palavra-chave e grava as
ofertas já com o link de afiliado (`offerLink`), então não passa pela extensão. A assinatura é
SHA256 de AppID + timestamp + corpo + Secret, no header Authorization.

Os nomes dos campos seguem a documentação da Open API do Brasil; a primeira coleta com as
credenciais reais confirma. Resposta fora do esperado vira erro do job (aviso no Telegram).
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..config import ShopeeSearch, ShopeeSource
from ..models import Offer, utcnow
from ..sources import SHOPEE, make_id

ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"
QUERY = """query ($keyword: String, $sortType: Int, $page: Int, $limit: Int) {
  productOfferV2(keyword: $keyword, sortType: $sortType, page: $page, limit: $limit) {
    nodes { itemId productName commissionRate priceMin priceMax priceDiscountRate sales
            ratingStar imageUrl offerLink productLink shopName }
  }
}"""
SORT_BY_SALES = 2  # 1 relevância, 2 mais vendidos, 3/4 preço, 5 comissão


class ShopeeError(Exception):
    pass


def signature(app_id: str, secret: str, timestamp: int, payload: str) -> str:
    return hashlib.sha256(f"{app_id}{timestamp}{payload}{secret}".encode()).hexdigest()


@dataclass
class ShopeeClient:
    http: Any  # httpx.AsyncClient
    app_id: str
    secret: str
    clock: Any = time.time

    async def offers(self, keyword: str, limit: int) -> list[dict]:
        body = {
            "query": QUERY,
            "variables": {"keyword": keyword, "sortType": SORT_BY_SALES, "page": 1, "limit": limit},
        }
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        ts = int(self.clock())
        auth = (
            f"SHA256 Credential={self.app_id}, Timestamp={ts}, "
            f"Signature={signature(self.app_id, self.secret, ts, payload)}"
        )
        response = await self.http.post(
            ENDPOINT,
            content=payload.encode(),
            timeout=30,
            headers={"Authorization": auth, "Content-Type": "application/json"},
        )
        data = response.json()
        if response.status_code != 200 or data.get("errors"):
            message = (data.get("errors") or [{}])[0].get("message", response.text[:200])
            raise ShopeeError(f"Shopee {response.status_code}: {message}")
        try:
            return data["data"]["productOfferV2"]["nodes"] or []
        except (KeyError, TypeError) as e:
            raise ShopeeError(f"resposta inesperada da Shopee: {str(data)[:200]}") from e


def _float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_nodes(
    nodes: list[dict], search: ShopeeSearch, now: datetime | None = None
) -> list[Offer]:
    """Nós do `productOfferV2` → `Offer`. A comissão vem em fração ("0.07" = 7%); o preço "de"
    sai do % de desconto, que a Shopee manda inteiro."""
    now = now or utcnow()
    offers = []
    for n in nodes:
        price = _float(n.get("priceMin"))
        link = n.get("offerLink")
        if not n.get("itemId") or price is None or not link:
            continue
        discount = _float(n.get("priceDiscountRate")) or 0
        # arredonda para cima: o % recalculado não pode ficar abaixo do que a Shopee anuncia
        original = (
            math.ceil(price / (1 - discount / 100) * 100) / 100 if 0 < discount < 100 else None
        )
        rate = _float(n.get("commissionRate")) or 0
        offers.append(
            Offer(
                mlb_id=make_id(SHOPEE, n["itemId"]),
                title=n.get("productName") or str(n["itemId"]),
                price=price,
                original_price=original,
                commission_pct=round(rate * 100 if rate <= 1 else rate, 2),
                category_path=(search.category,),
                permalink=n.get("productLink") or link,
                image_url=n.get("imageUrl"),
                rating=_float(n.get("ratingStar")),
                sold_count=int(n["sales"]) if n.get("sales") else None,
                item_type="shopee",
                affiliate_link=link,
                collected_at=now,
            )
        )
    return offers


async def collect(
    client: ShopeeClient, src: ShopeeSource, now: datetime | None = None
) -> list[Offer]:
    found: dict[str, Offer] = {}
    for search in src.searches:
        for offer in parse_nodes(await client.offers(search.keyword, src.limit), search, now):
            found.setdefault(offer.mlb_id, offer)  # a primeira busca define a categoria
    return list(found.values())
