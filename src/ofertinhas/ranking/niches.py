from collections.abc import Sequence

from ..config import NicheConfig
from ..models import Offer
from .filters import contains_term, normalize_text


def match_niches(
    offer: Offer, niches: Sequence[NicheConfig], search: str | None = None
) -> list[str]:
    """Nichos da oferta, na ordem da config.

    A categoria tem precedência: se algum nicho casa por categoria (em qualquer nível da
    árvore), as keywords não são consultadas. `search` é o termo da busca que trouxe a
    oferta: os nichos com esse termo em `search_terms` entram também, porque a busca sem
    filtro de categoria não diz a categoria da oferta.
    """
    path = set(offer.category_path)
    matched = {n.name for n in niches if path.intersection(n.categories)}
    if not matched:
        title = normalize_text(offer.title)
        matched = {n.name for n in niches if any(contains_term(title, k) for k in n.keywords)}
    if search and (term := normalize_text(search)):
        matched |= {
            n.name for n in niches if any(normalize_text(t) == term for t in n.search_terms)
        }
    return [n.name for n in niches if n.name in matched]
