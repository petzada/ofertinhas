import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def utcnow() -> datetime:
    return datetime.now(UTC)


class CandidateState(StrEnum):
    """Estado de uma oferta dentro de um nicho."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISCARDED = "discarded"
    LINKED = "linked"
    LINK_FAILED = "link_failed"
    RENDERED = "rendered"
    QUEUED = "queued"
    POSTED = "posted"
    EXPIRED = "expired"


# Ainda no fluxo de publicação: não pode ser ranqueada de novo.
ACTIVE_STATES = frozenset(
    {
        CandidateState.PENDING,
        CandidateState.APPROVED,
        CandidateState.LINKED,
        CandidateState.LINK_FAILED,
        CandidateState.RENDERED,
        CandidateState.QUEUED,
    }
)
# Só volta depois do cooldown ou com queda de preço.
COOLDOWN_STATES = frozenset({CandidateState.POSTED, CandidateState.REJECTED})


@dataclass
class Offer:
    """Produto como visto no portal de afiliados."""

    mlb_id: str
    title: str
    price: float
    commission_pct: float
    category_path: tuple[str, ...]  # da raiz até a folha; vazia quando a coleta não filtrou
    permalink: str
    original_price: float | None = None
    image_url: str | None = None
    rating: float | None = None
    sold_count: int | None = None
    item_type: str = "product"  # "product" ou "user_product", como o createLink espera
    extra_commission: bool = False  # selo "ganhos extras" do portal
    pix_only: bool = False  # o desconto vale só no Pix
    international: bool = False  # compra internacional
    highlight: str | None = None  # "MAIS VENDIDO", "OFERTA IMPERDÍVEL"…
    # Frete grátis e Full vêm da página do produto, não da lista do portal.
    free_shipping: bool = False
    full: bool = False
    shipping_checked_at: datetime | None = None
    collected_at: datetime = field(default_factory=utcnow)  # primeira vez vista
    affiliate_link: str | None = None
    last_seen_at: datetime | None = None  # última coleta em que apareceu (vem do banco)

    @property
    def category_id(self) -> str | None:
        return self.category_path[-1] if self.category_path else None

    @property
    def discount_pct(self) -> float:
        """Desconto em % inteiro, arredondado para baixo como o ML anuncia (nunca exagera)."""
        if not self.original_price or self.original_price <= self.price:
            return 0.0
        return float(math.floor((1 - self.price / self.original_price) * 100 + 1e-9))

    @property
    def commission_brl(self) -> float:
        return round(self.price * self.commission_pct / 100, 2)


@dataclass
class Candidate:
    """Decisão sobre uma oferta em um nicho e seu progresso até a postagem."""

    mlb_id: str
    niche: str
    state: CandidateState
    score: float
    breakdown: dict[str, float]  # pontos por critério; somam `score`
    ref_price: float  # preço no momento da decisão, base do cooldown de repost
    decided_at: datetime
    caption: str | None = None
    card_path: str | None = None
    notified_at: datetime | None = None
