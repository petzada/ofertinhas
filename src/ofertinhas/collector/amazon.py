"""Ofertas do Dia da Amazon (`/d2b/api/v1/products/search`), lidas pela extensão no Brave.

É a mesma chamada que a página de ofertas faz: GET sem token, 30 ofertas por página
(`startIndex`), filtrada por departamento (`includedDepartments`). Não há API de afiliado sem
10 vendas em 30 dias (Creators API), então o link é a URL do produto com a tag de associado.
Formato mapeado em 05/11/2026 (`tests/fixtures/amazon/deals.json`).
"""

import json
from datetime import datetime
from urllib.parse import quote

from ..config import AmazonSource
from ..models import Offer, utcnow
from ..sources import AMAZON, make_id

SEARCH_PATH = "/d2b/api/v1/products/search"
BASE = "https://www.amazon.com.br"
PAGE_SIZE = 30

# departamento da Amazon → (nome, categoria raiz MLB equivalente, usada pelos nichos)
DEPARTMENTS: dict[str, tuple[str, str]] = {
    "16194415011": ("Beleza", "MLB1246"),
    "16215418011": ("Saúde e Bem-Estar", "MLB264586"),
    "16191001011": ("Casa", "MLB1574"),
    "16957126011": ("Cozinha", "MLB1574"),
    "16522083011": ("Eletrodomésticos", "MLB5726"),
    "17365812011": ("Moda", "MLB1430"),
    "16209063011": ("Eletrônicos e Tecnologia", "MLB1000"),
    "16339927011": ("Computadores e Informática", "MLB1648"),
    "7791986011": ("Games e Consoles", "MLB1144"),
    "18991137011": ("Pet Shop", "MLB1071"),
    "17242604011": ("Bebês", "MLB1384"),
    "16194300011": ("Brinquedos e Jogos", "MLB1132"),
    "17349397011": ("Esporte, Aventura e Lazer", "MLB1276"),
    "18914210011": ("Automotivo", "MLB5672"),
    "16957183011": ("Ferramentas e Materiais de Construção", "MLB263532"),
}


def departments_for(src: AmazonSource, categories: list[str]) -> list[str]:
    """Departamentos a ler: os do config ou, sem lista, os que casam com as categorias dos
    nichos ativos."""
    if src.departments:
        return src.departments
    wanted = set(categories)
    return [dep for dep, (_, mlb) in DEPARTMENTS.items() if mlb in wanted]


def search_url(department: str, start: int) -> str:
    filters = {
        "includedDepartments": [department],
        "excludedDepartments": [],
        "includedTags": [],
        "excludedTags": ["restrictedcontent"],
        "promotionTypes": ["LIGHTNING_DEAL", "BEST_DEAL"],
        "accessTypes": [],
        "brandIds": [],
        "unifiedIds": [],
    }
    ranking = {"pageTypeId": "deals", "rankGroup": "PARENT_ASIN_RANKING"}
    return (
        f"{BASE}{SEARCH_PATH}?pageSize={PAGE_SIZE}&startIndex={start}"
        f"&rankingContext={quote(json.dumps(ranking, separators=(',', ':')))}"
        f"&filters={quote(json.dumps(filters, separators=(',', ':')))}"
    )


def collect_requests(src: AmazonSource, categories: list[str]) -> list[dict]:
    return [
        {"url": search_url(dep, page * PAGE_SIZE), "department": dep}
        for dep in departments_for(src, categories)
        for page in range(src.pages_per_department)
    ]


def affiliate_link(asin: str, tag: str) -> str:
    return f"{BASE}/dp/{asin}?tag={tag}"


def _price(block: dict | None) -> float | None:
    try:
        return float(block["price"]) if block else None
    except (KeyError, TypeError, ValueError):
        return None


def _rating(product: dict) -> float | None:
    text = (product.get("customerReviews") or {}).get("rating", {}).get("shortDisplayString")
    try:
        return float(text.replace(",", ".")) if text else None
    except ValueError:
        return None


def _category(product: dict, department: str | None) -> tuple[str, ...]:
    ids = list((product.get("meta") or {}).get("departmentIds") or [])
    if department:
        ids.insert(0, department)
    for dep in ids:
        if dep in DEPARTMENTS:
            return (DEPARTMENTS[dep][1],)
    return ()


def parse_deals(
    body: dict, src: AmazonSource, department: str | None = None, now: datetime | None = None
) -> list[Offer]:
    """Resposta da busca de ofertas → `Offer` já com link de afiliado. Ofertas esgotadas, sem
    preço ou sem preço "de" (sem desconto para mostrar) ficam de fora."""
    now = now or utcnow()
    offers = []
    for p in body.get("products") or []:
        asin = p.get("asin")
        price_block = p.get("price") or {}
        price = _price(price_block.get("priceToPay"))
        original = _price(price_block.get("basisPrice"))
        state = (p.get("dealDetails") or {}).get("state", "AVAILABLE")
        if not asin or price is None or original is None or original <= price:
            continue
        if state != "AVAILABLE":
            continue
        category = _category(p, department)
        image = (p.get("image") or {}).get("hiRes") or (p.get("image") or {}).get("lowRes")
        reviews = (p.get("customerReviews") or {}).get("count", {}).get("value")
        offers.append(
            Offer(
                mlb_id=make_id(AMAZON, asin),
                title=p.get("title") or asin,
                price=price,
                original_price=original,
                commission_pct=src.commission_pct.get(
                    category[0] if category else "", src.default_commission_pct
                ),
                category_path=category,
                permalink=f"{BASE}/dp/{asin}",
                image_url=f"{image['baseUrl']}.{image.get('extension', 'jpg')}" if image else None,
                rating=_rating(p),
                sold_count=int(reviews) if reviews else None,  # sem vendidos: nº de avaliações
                item_type="amazon",
                highlight="OFERTA RELÂMPAGO"
                if p.get("dealDetails", {}).get("type") == "LIGHTNING_DEAL"
                else None,
                affiliate_link=affiliate_link(asin, src.tag),
                collected_at=now,
            )
        )
    return offers
