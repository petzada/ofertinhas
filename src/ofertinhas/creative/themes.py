"""Cores do card de cada nicho. O texto do topo é a marca (`brand` do config), sem categoria.
Nicho sem cores próprias usa o padrão."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Theme:
    bg: str  # fundo do card
    badge: str  # selo de % OFF
    price: str  # preço "por"
    label: str = ""  # faixa do topo do card (a marca, preenchida por theme_for)
    text: str = "#1F1F1F"
    muted: str = "#8A8A8A"
    panel: str = "#FFFFFF"
    footer: str = "#FFFFFF"  # texto sobre o fundo


DEFAULT = Theme(bg="#FF5A1F", badge="#D7142B", price="#0B7A3B")

THEMES = {
    "casa": Theme(bg="#1F7A68", badge="#E8452C", price="#1F7A68"),
    "tech": Theme(bg="#3B2F8F", badge="#FF3D71", price="#3B2F8F"),
    "beleza": Theme(bg="#B83280", badge="#E8452C", price="#B83280"),
    "moda": Theme(bg="#2D2D2D", badge="#E8452C", price="#2D2D2D"),
    "infantil": Theme(bg="#2B8FD6", badge="#FF6B35", price="#1F6FAA"),
    "pets": Theme(bg="#8A5A3C", badge="#E8452C", price="#8A5A3C"),
    "esporte": Theme(bg="#1E7B34", badge="#FF3D3D", price="#1E7B34"),
    "auto": Theme(bg="#37474F", badge="#FF5A1F", price="#37474F"),
}


def theme_for(niche: str, brand: str) -> Theme:
    return replace(THEMES.get(niche, DEFAULT), label=brand.upper())
