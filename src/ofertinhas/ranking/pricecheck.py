"""Desconto inflado: o preço "de" que sobe pouco antes da promoção, ou um "por" que já foi menor.

Só conta o que a coleta viu (`price_history`); sem histórico, a oferta passa como veio. Com
histórico, duas regras, ambas com uma folga (`tolerance_pct`) para a oscilação normal:

- o preço já foi menor dentro da janela: a "promoção" não é o melhor preço recente, então o
  desconto real é zero (e a regra de desconto descarta);
- o preço "de" subiu dentro da janela: o desconto passa a ser contado sobre o menor "de"
  visto, o que valia antes de inflar.
"""

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from ..config import PriceCheck
from ..models import Offer

PricePoint = tuple[datetime, float, float | None]  # (desde quando, preço, preço "de")


@dataclass(frozen=True)
class PriceVerdict:
    offer: Offer  # com o "de" honesto; a mesma oferta quando o histórico não muda nada
    reason: str | None = None  # por que o desconto foi corrigido

    @property
    def inflated(self) -> bool:
        return self.reason is not None


def check_price(offer: Offer, points: Sequence[PricePoint], check: PriceCheck) -> PriceVerdict:
    if not check.enabled or not points:
        return PriceVerdict(offer)
    slack = check.tolerance_pct / 100
    lowest = min(price for _, price, _ in points)
    if lowest < offer.price * (1 - slack):
        return PriceVerdict(
            dataclasses.replace(offer, original_price=None),
            f"já custou R$ {lowest:.2f} nos últimos {check.lookback_days} dias "
            f"(hoje R$ {offer.price:.2f})",
        )
    originals = [original for _, _, original in points if original]
    if offer.original_price and originals:
        base = min(originals)
        if offer.original_price > base * (1 + slack):
            return PriceVerdict(
                dataclasses.replace(offer, original_price=base),
                f'preço "de" subiu de R$ {base:.2f} para R$ {offer.original_price:.2f}',
            )
    return PriceVerdict(offer)
