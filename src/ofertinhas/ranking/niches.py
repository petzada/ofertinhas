from collections.abc import Sequence

from ..config import NicheConfig
from ..models import Offer
from .filters import contains_term, normalize_text


def match_niches(offer: Offer, niches: Sequence[NicheConfig]) -> list[str]:
    """Nichos da oferta, na ordem da config.

    A categoria tem precedência: se algum nicho casa por categoria (em qualquer nível da
    árvore), as keywords não são consultadas.
    """
    path = set(offer.category_path)
    by_category = [n.name for n in niches if path.intersection(n.categories)]
    if by_category:
        return by_category
    title = normalize_text(offer.title)
    return [n.name for n in niches if any(contains_term(title, k) for k in n.keywords)]
