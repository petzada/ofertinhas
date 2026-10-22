import re
import unicodedata

from ..config import Filters
from ..models import Offer


def normalize_text(text: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados, para comparar termos."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def contains_term(normalized_text: str, term: str) -> bool:
    """`term` aparece como palavra(s) inteira(s) em `normalized_text`; com `*` no fim, vale
    como começo de palavra (`panela*` casa com "panela" e "panelas")."""
    prefix = term.endswith("*")
    body = re.escape(normalize_text(term.rstrip("*")))
    pattern = rf"(?<!\w){body}" + ("" if prefix else r"(?!\w)")
    return re.search(pattern, normalized_text) is not None


def passes(offer: Offer, filters: Filters) -> tuple[bool, str | None]:
    """Devolve se a oferta passa nos filtros e, se não passar, o motivo."""
    if not filters.min_price <= offer.price <= filters.max_price:
        return False, f"preço R$ {offer.price:.2f} fora da faixa"
    if (
        filters.min_rating is not None
        and offer.rating is not None
        and offer.rating < filters.min_rating
    ):
        return False, f"avaliação {offer.rating} abaixo de {filters.min_rating}"
    if filters.require_free_shipping and not offer.free_shipping:
        return False, "sem frete grátis"
    if filters.require_full and not offer.full:
        return False, "não é Full"
    if filters.exclude_international and offer.international:
        return False, "compra internacional"
    title = normalize_text(offer.title)
    for keyword in filters.blocked_keywords:
        if contains_term(title, keyword):
            return False, f"palavra bloqueada: {keyword}"
    if filters.required_keywords and not any(
        contains_term(title, k) for k in filters.required_keywords
    ):
        return False, "nenhum termo do nicho no título"
    return True, None
