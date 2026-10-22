"""Configuração do `config.yaml`: perfis de ranking, nichos e ritmo de postagem.

Cada nicho é montado em camadas: `defaults` → `niches.<nome>` → overrides gravados
pelo bot no banco. Só o que muda precisa ser declarado em cada camada.
"""

import re
from collections.abc import Mapping
from datetime import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConfigError(ValueError):
    pass


# O nome do nicho vai no callback_data do Telegram (máx. 64 bytes) e não pode ter ":".
NICHE_NAME = re.compile(r"[a-z0-9_-]{1,20}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Weights(_Strict):
    commission_pct: float = Field(35, ge=0)
    discount_pct: float = Field(25, ge=0)
    commission_brl: float = Field(15, ge=0)
    rating: float = Field(10, ge=0)
    sold_count: float = Field(10, ge=0)
    freshness: float = Field(5, ge=0)
    free_shipping: float = Field(8, ge=0)
    full: float = Field(7, ge=0)

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
    blocked_keywords: list[str] = ["usado", "recondicionado", "réplica"]

    @model_validator(mode="after")
    def _price_range(self):
        if self.min_price >= self.max_price:
            raise ValueError("min_price deve ser menor que max_price")
        return self


class Pacing(_Strict):
    min_interval_min: int = Field(25, ge=1)
    jitter_min: int = Field(5, ge=0)
    window: tuple[time, time] = (time(8, 0), time(23, 0))
    max_posts_per_day: int = Field(25, ge=1)
    whatsapp_between_groups_s: tuple[int, int] = (30, 90)

    @field_validator("window", mode="before")
    @classmethod
    def _window_needs_quotes(cls, v):
        if isinstance(v, list | tuple) and any(isinstance(x, int) for x in v):
            raise ValueError('horários da janela precisam de aspas no YAML: ["08:00", "23:00"]')
        return v

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


class Profile(_Strict):
    weights: Weights = Weights()
    targets: Targets = Targets()
    filters: Filters = Filters()
    auto_approve_at: float = Field(80, ge=0, le=100)
    manual_review_at: float = Field(60, ge=0, le=100)
    repost_cooldown_days: int = Field(7, ge=0)
    repost_price_drop_pct: float = Field(10, ge=0, le=100)
    pacing: Pacing = Pacing()

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

    @model_validator(mode="after")
    def _routing_and_channels(self):
        if not self.categories and not self.keywords:
            raise ValueError("defina categories ou keywords")
        if self.telegram_chat_id is None and not self.whatsapp_group_jid:
            raise ValueError("defina ao menos um canal (telegram_chat_id ou whatsapp_group_jid)")
        return self


class AppConfig(_Strict):
    defaults: dict[str, Any] = {}
    niches: dict[str, dict[str, Any]]
    multi_niche: bool = False  # oferta vai para todos os nichos que casar, não só o de maior nota

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
            self.for_niche(name)
        return self

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppConfig":
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise ConfigError(_describe(e)) from None

    def niche_names(self) -> list[str]:
        return list(self.niches)

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
