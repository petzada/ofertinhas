"""Configuração do `config.yaml`: perfis de ranking, nichos e ritmo de postagem.

Cada nicho é montado em camadas: `defaults` → `niches.<nome>` → overrides gravados
pelo bot no banco. Só o que muda precisa ser declarado em cada camada.
"""

import re
from collections.abc import Mapping
from datetime import time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .collector.categories import ROOT_CATEGORIES


class ConfigError(ValueError):
    pass


# O nome do nicho vai no callback_data do Telegram (máx. 64 bytes) e não pode ter ":".
NICHE_NAME = re.compile(r"[a-z0-9_-]{1,20}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _reject_unquoted_times(v):
    # YAML 1.1 lê 23:00 sem aspas como número sexagesimal (1380).
    if isinstance(v, list | tuple) and any(isinstance(x, int) for x in v):
        raise ValueError('horários da janela precisam de aspas no YAML: ["08:00", "23:00"]')
    return v


class Weights(_Strict):
    commission_pct: float = Field(35, ge=0)
    discount_pct: float = Field(25, ge=0)
    commission_brl: float = Field(15, ge=0)
    rating: float = Field(10, ge=0)
    sold_count: float = Field(10, ge=0)
    freshness: float = Field(5, ge=0)
    # Zerados: o portal não informa frete grátis nem Full (ver docs/notes/portal-mapping.md).
    free_shipping: float = Field(0, ge=0)
    full: float = Field(0, ge=0)

    @model_validator(mode="after")
    def _not_all_zero(self):
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("ao menos um peso precisa ser maior que zero")
        return self


class Targets(_Strict):
    """Valor que vale nota máxima em cada critério (normalização absoluta)."""

    commission_pct: float = Field(20, gt=0)
    discount_pct: float = Field(60, gt=0)
    commission_brl: float = Field(40, gt=0)
    sold_count: int = Field(5000, gt=0)
    rating_floor: float = Field(4.0, ge=0, lt=5)  # avaliação igual ou abaixo vale 0
    freshness_hours: float = Field(24, gt=0)


class Filters(_Strict):
    min_price: float = Field(15, ge=0)
    max_price: float = Field(3000, gt=0)
    min_rating: float | None = Field(4.0, ge=0, le=5)  # sem avaliação passa
    require_free_shipping: bool = False
    require_full: bool = False
    exclude_international: bool = False
    blocked_keywords: list[str] = ["usado", "recondicionado", "réplica"]
    # Com algum termo, o título precisa ter ao menos um (nicho fino dentro de categorias
    # largas, ex.: enxoval dentro de Casa). `*` no fim pega o começo da palavra: `panela*`.
    required_keywords: list[str] = []

    @model_validator(mode="after")
    def _price_range(self):
        if self.min_price >= self.max_price:
            raise ValueError("min_price deve ser menor que max_price")
        return self


class PriceCheck(_Strict):
    """Confere o desconto anunciado com o histórico de preços da coleta (ranking/pricecheck)."""

    enabled: bool = True
    lookback_days: int = Field(30, ge=1)  # janela do histórico, como a regra de 30 dias
    tolerance_pct: float = Field(5, ge=0, le=50)  # oscilação normal que não conta como truque


class Pacing(_Strict):
    min_interval_min: int = Field(25, ge=1)
    jitter_min: int = Field(5, ge=0)
    window: tuple[time, time] = (time(8, 0), time(23, 0))
    max_posts_per_day: int = Field(25, ge=1)
    whatsapp_between_groups_s: tuple[int, int] = (30, 90)

    _window_needs_quotes = field_validator("window", mode="before")(_reject_unquoted_times)

    @model_validator(mode="after")
    def _ranges(self):
        if self.window[0] >= self.window[1]:
            raise ValueError("window: o início deve ser antes do fim")
        if self.jitter_min >= self.min_interval_min:
            raise ValueError("jitter_min deve ser menor que min_interval_min")
        low, high = self.whatsapp_between_groups_s
        if not 0 <= low <= high:
            raise ValueError("whatsapp_between_groups_s deve ser [mínimo, máximo]")
        return self


WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")  # índice = date.weekday()


class PollSchedule(_Strict):
    """Enquete semanal no grupo de WhatsApp do nicho; as perguntas ficam em `polls.BANK`."""

    weekday: Literal["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    at: time  # horário de SP; fora do sistema na hora, a enquete ainda sai até 2 h depois

    @field_validator("at", mode="before")
    @classmethod
    def _at_needs_quotes(cls, v):
        if isinstance(v, int):  # YAML 1.1 lê 19:30 sem aspas como número
            raise ValueError('o horário precisa de aspas no YAML: at: "19:30"')
        return v


class Gate(_Strict):
    """Mínimos de desconto e comissão. `strict`: "mais de" (>) em vez de "a partir de" (≥)."""

    min_discount_pct: float = Field(0, ge=0, le=100)
    min_commission_pct: float = Field(0, ge=0, le=100)
    strict: bool = False

    def passes(self, discount_pct: float, commission_pct: float) -> bool:
        if self.strict:
            return discount_pct > self.min_discount_pct and commission_pct > self.min_commission_pct
        return discount_pct >= self.min_discount_pct and commission_pct >= self.min_commission_pct


class SourceGates(_Strict):
    auto: Gate
    review: Gate


class Rules(_Strict):
    """Decide pela oferta em vez da nota: passa em `auto` → link automático; senão, passa em
    `review` → card para o admin; senão, descarte. A nota só ordena quem pega a cota.

    `amazon`/`shopee` trocam os dois cortes para ofertas dessa loja (a Amazon paga comissão
    fixa por categoria, então a regra dela costuma olhar só o desconto)."""

    auto: Gate
    review: Gate
    amazon: SourceGates | None = None
    shopee: SourceGates | None = None

    def manual_tier(self, source: str) -> bool:
        """Há faixa de aprovação manual (card no bot) só se `review` for mais solta que `auto`.
        Com as duas iguais, quem passa entra direto e o resto é descartado."""
        auto, review = self.for_source(source)
        return review != auto

    def for_source(self, source: str) -> tuple[Gate, Gate]:
        gates = getattr(self, source, None) if source in ("amazon", "shopee") else None
        return (gates.auto, gates.review) if gates else (self.auto, self.review)


class Profile(_Strict):
    weights: Weights = Weights()
    targets: Targets = Targets()
    filters: Filters = Filters()
    price_check: PriceCheck = PriceCheck()
    auto_approve_at: float = Field(80, ge=0, le=100)
    manual_review_at: float = Field(60, ge=0, le=100)
    rules: Rules | None = None  # se definido, decide no lugar dos cortes por nota
    # Cota diária (horário de SP): só as melhores do dia passam, o resto espera o dia seguinte.
    max_auto_per_day: int = Field(10, ge=0)
    max_review_per_day: int = Field(8, ge=0)  # cards de aprovação para você
    repost_cooldown_days: int = Field(7, ge=0)
    repost_price_drop_pct: float = Field(10, ge=0, le=100)
    max_offer_age_hours: float = Field(6, gt=0)  # sem reaparecer na coleta, expira
    pacing: Pacing = Pacing()  # Telegram (e WhatsApp, se `whatsapp_pacing` não for definido)
    whatsapp_pacing: Pacing | None = None  # ritmo e janela próprios do WhatsApp

    @model_validator(mode="after")
    def _thresholds(self):
        if self.manual_review_at >= self.auto_approve_at:
            raise ValueError("manual_review_at deve ser menor que auto_approve_at")
        return self


class NicheConfig(Profile):
    name: str
    template: str
    categories: list[str] = []
    keywords: list[str] = []
    telegram_chat_id: int | None = None
    whatsapp_group_jid: str | None = None
    paused: bool = False
    polls: PollSchedule | None = None  # só para nicho com whatsapp_group_jid

    def destination(self) -> tuple[int | None, str | None]:
        """Grupo(s) onde o nicho posta; nichos com o mesmo destino dividem a fila e o ritmo."""
        return self.telegram_chat_id, self.whatsapp_group_jid

    @model_validator(mode="after")
    def _routing_and_channels(self):
        if not self.categories and not self.keywords:
            raise ValueError("defina categories ou keywords")
        unknown = [c for c in self.categories if c not in ROOT_CATEGORIES]
        if unknown:
            raise ValueError(
                f"categorias que o portal não filtra: {', '.join(unknown)} "
                "(use só categorias raiz; veja collector/categories.py)"
            )
        if self.telegram_chat_id is None and not self.whatsapp_group_jid:
            raise ValueError("defina ao menos um canal (telegram_chat_id ou whatsapp_group_jid)")
        if self.polls and not self.whatsapp_group_jid:
            raise ValueError("polls precisa de whatsapp_group_jid (a enquete só sai no WhatsApp)")
        return self


class CollectorConfig(_Strict):
    """Ritmo da extensão no portal (entregue a ela em /ext/config)."""

    every_min: int = Field(20, ge=5)
    jitter_min: int = Field(5, ge=0)
    pages_per_category: int = Field(3, ge=1, le=10)
    # Categorias por ciclo, em rodízio: cobre todos os nichos sem aumentar as chamadas ao ML.
    categories_per_cycle: int = Field(6, ge=1)
    request_gap_s: tuple[int, int] = (5, 15)  # entre chamadas de busca
    include_unfiltered: bool = False  # também busca a lista geral (nicho só por keywords)
    window: tuple[time, time] | None = None  # None: coleta e links a qualquer hora
    max_links_per_hour: int = Field(30, ge=1)
    link_gap_s: tuple[int, int] = (30, 90)  # entre links gerados
    # Estoque-alvo: só pede link quando o que já tem link não cobre os posts das próximas
    # `stock_hours` horas (+ `stock_extra` de folga). O resto das aprovadas espera na reserva.
    stock_hours: float = Field(6, gt=0)
    stock_extra: int = Field(2, ge=0)
    # Estoque abaixo do alvo mesmo com todas as aprovadas: a nuvem pede uma coleta fora de
    # hora (`collect_now` no /ext/config), no máximo uma a cada `collect_now_gap_min`.
    collect_now_gap_min: int = Field(30, ge=5)

    _window_needs_quotes = field_validator("window", mode="before")(_reject_unquoted_times)

    @model_validator(mode="after")
    def _ranges(self):
        for name in ("request_gap_s", "link_gap_s"):
            low, high = getattr(self, name)
            if not 0 <= low <= high:
                raise ValueError(f"{name} deve ser [mínimo, máximo]")
        if self.window and self.window[0] >= self.window[1]:
            raise ValueError("window: o início deve ser antes do fim")
        if self.jitter_min >= self.every_min:
            raise ValueError("jitter_min deve ser menor que every_min")
        return self


class LandingConfig(_Strict):
    """Página de entrada no grupo (`/grupo` do Worker), destino dos anúncios."""

    group_url: str = Field(pattern=r"^https://chat\.whatsapp\.com/[A-Za-z0-9]+$")
    name: str = Field("Grupo VIP de Achadinhos", min_length=1, max_length=40)
    pixel_id: str | None = Field(None, pattern=r"^[0-9]{6,20}$")  # Pixel da Meta (evento Lead)
    # Banner azul abaixo da dobra: grupo do Telegram com ofertas de tudo (clique = TelegramClick)
    telegram_url: str | None = Field(None, pattern=r"^https://t\.me/[A-Za-z0-9_+]+$")


class AmazonSource(_Strict):
    """Ofertas do Dia da Amazon, lidas pela extensão no Brave (sem API: o link é a URL do
    produto com a tag de associado). Ver collector/amazon.py."""

    tag: str = Field(pattern=r"^[A-Za-z0-9-]+-20$")
    # departamentos da Amazon (IDs em collector/amazon.py); vazio: os que casam com os nichos
    departments: list[str] = []
    pages_per_department: int = Field(2, ge=1, le=5)  # 30 ofertas por página
    every_min: int = Field(120, ge=30)  # leitura a cada 2 h (com folga para não ser bloqueado)
    # comissão por categoria raiz MLB equivalente; confira na tabela de taxas do Associados
    commission_pct: dict[str, float] = {}
    default_commission_pct: float = Field(4, ge=0, le=100)


class ShopeeSearch(_Strict):
    keyword: str = Field(min_length=2)
    category: str  # categoria raiz MLB equivalente, para rotear aos nichos


class ShopeeSource(_Strict):
    """Open API de afiliados da Shopee (GraphQL), coletada na nuvem: já vem com o link."""

    searches: list[ShopeeSearch] = Field(min_length=1)
    limit: int = Field(30, ge=1, le=50)  # ofertas por busca (job `shopee_collect`, de hora em hora)

    @model_validator(mode="after")
    def _known_categories(self):
        unknown = [s.category for s in self.searches if s.category not in ROOT_CATEGORIES]
        if unknown:
            raise ValueError(f"shopee: categorias desconhecidas: {', '.join(unknown)}")
        return self


class SourcesConfig(_Strict):
    amazon: AmazonSource | None = None
    shopee: ShopeeSource | None = None


class AdsConfig(_Strict):
    """Campanhas da Meta cujo gasto entra no ROAS do status (job `ads_sync`, `roas.py`)."""

    meta_account_id: str = Field(pattern=r"^act_[0-9]+$")
    campaign_name_contains: str = ""  # vazio: todas as campanhas da conta


class AppConfig(_Strict):
    defaults: dict[str, Any] = {}
    niches: dict[str, dict[str, Any]]
    multi_niche: bool = False  # oferta vai para todos os nichos que casar, não só o de maior nota
    collector: CollectorConfig = CollectorConfig()
    whatsapp_enabled: bool = False  # trava: nada é enviado ao WhatsApp enquanto for false
    x_enabled: bool = False  # trava do X: com true, cada post do Telegram também sai no X
    brand: str = Field("Ofertas 2KAI", min_length=1, max_length=30)  # topo do card
    # Limpeza diária: ofertas, decisões e histórico de preço mais velhos que isso saem do banco.
    retention_days: int = Field(60, ge=14)
    sources: SourcesConfig = SourcesConfig()  # lojas além do Mercado Livre
    ads: AdsConfig | None = None  # gasto da Meta no status; precisa do META_ADS_TOKEN
    landing: LandingConfig | None = None  # página /grupo; sem ela a rota responde 404

    @model_validator(mode="after")
    def _validate_layers(self):
        if not self.niches:
            raise ValueError("defina ao menos um nicho")
        bad = [n for n in self.niches if not NICHE_NAME.fullmatch(n)]
        if bad:
            raise ValueError(
                f"nome do nicho inválido: {', '.join(bad)} "
                "(use até 20 letras minúsculas, números, _ ou -)"
            )
        try:
            Profile(**self.defaults)
        except ValidationError as e:
            raise ConfigError(f"defaults: {_describe(e)}") from None
        for name in self.niches:
            niche = self.for_niche(name)
            if self.retention_days <= max(
                niche.repost_cooldown_days, niche.price_check.lookback_days
            ):
                raise ConfigError(
                    f"retention_days ({self.retention_days}) precisa ser maior que o cooldown "
                    f"de repost e a janela do price_check do nicho '{name}'"
                )
        return self

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppConfig":
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise ConfigError(_describe(e)) from None

    def niche_names(self) -> list[str]:
        return list(self.niches)

    def collector_categories(self, paused: set[str]) -> list[str]:
        """Categorias a coletar, na ordem da config, sem repetir e só de nichos ativos."""
        seen: dict[str, None] = {}
        for name, raw in self.niches.items():
            if name not in paused:
                seen.update(dict.fromkeys(raw.get("categories", [])))
        return list(seen)

    def for_niche(self, name: str, overrides: Mapping[str, Any] | None = None) -> NicheConfig:
        if name not in self.niches:
            raise KeyError(name)
        data = deep_merge(self.defaults, self.niches[name])
        if overrides:
            data = deep_merge(data, overrides)
        data.setdefault("template", name)
        try:
            return NicheConfig(name=name, **data)
        except ValidationError as e:
            raise ConfigError(f"nicho '{name}': {_describe(e)}") from None


def load_config_text(text: str) -> AppConfig:
    return AppConfig.from_dict(yaml.safe_load(text) or {})


def load_config(path: str | Path) -> AppConfig:
    return load_config_text(Path(path).read_text(encoding="utf-8"))


def deep_merge(base: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _describe(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = err["msg"].removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)
