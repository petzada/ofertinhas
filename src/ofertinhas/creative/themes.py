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
    "beleza": Theme(label="ACHADINHOS • BELEZA", bg="#B83280", badge="#E8452C", price="#B83280"),
    "moda": Theme(label="ACHADINHOS • MODA", bg="#2D2D2D", badge="#E8452C", price="#2D2D2D"),
    "infantil": Theme(label="ACHADINHOS • INFANTIL", bg="#2B8FD6", badge="#FF6B35",
                      price="#1F6FAA"),
    "pets": Theme(label="ACHADINHOS • PETS", bg="#8A5A3C", badge="#E8452C", price="#8A5A3C"),
    "esporte": Theme(label="ACHADINHOS • ESPORTE", bg="#1E7B34", badge="#FF3D3D",
                     price="#1E7B34"),
    "auto": Theme(label="ACHADINHOS • AUTO", bg="#37474F", badge="#FF5A1F", price="#37474F"),
}


def theme_for(niche: str) -> Theme:
    base = THEMES.get(niche, DEFAULT)
    if niche not in THEMES and niche:
        return Theme(**{**base.__dict__, "label": f"ACHADINHOS • {niche.upper()}"})
    return base
