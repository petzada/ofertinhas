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
    category_path: tuple[str, ...]  # da raiz até a folha
    permalink: str
    original_price: float | None = None
    image_url: str | None = None
    rating: float | None = None
    sold_count: int | None = None
    free_shipping: bool = False
    full: bool = False
    collected_at: datetime = field(default_factory=utcnow)  # primeira vez vista
    affiliate_link: str | None = None

    @property
    def category_id(self) -> str:
        return self.category_path[-1]

    @property
    def discount_pct(self) -> float:
        if not self.original_price or self.original_price <= self.price:
            return 0.0
        return round((1 - self.price / self.original_price) * 100, 1)

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
