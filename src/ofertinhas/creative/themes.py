"""Cores e rótulo do card de cada nicho. Nicho sem tema próprio usa o padrão."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    label: str  # faixa do topo do card
    bg: str  # fundo do card
    badge: str  # selo de % OFF
    price: str  # preço "por"
    text: str = "#1F1F1F"
    muted: str = "#8A8A8A"
    panel: str = "#FFFFFF"
    footer: str = "#FFFFFF"  # texto sobre o fundo


DEFAULT = Theme(label="ACHADINHOS DO DIA", bg="#FF5A1F", badge="#D7142B", price="#0B7A3B")

THEMES = {
    "casa": Theme(label="ACHADINHOS • CASA", bg="#1F7A68", badge="#E8452C", price="#1F7A68"),
    "tech": Theme(label="ACHADINHOS • TECH", bg="#3B2F8F", badge="#FF3D71", price="#3B2F8F"),
}


def theme_for(niche: str) -> Theme:
    base = THEMES.get(niche, DEFAULT)
    if niche not in THEMES and niche:
        return Theme(**{**base.__dict__, "label": f"ACHADINHOS • {niche.upper()}"})
    return base
