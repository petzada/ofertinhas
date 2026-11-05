"""Modelos de texto por tema: a oferta do nicho `mulher` ganha legenda do seu assunto."""

from pathlib import Path

import pytest

from ofertinhas.creative.text import caption_values, fill, load_templates, topic_of
from ofertinhas.models import Offer

TEMPLATES = Path(__file__).parents[1] / "templates" / "text"


def offer(title: str, root: str | None) -> Offer:
    return Offer(
        mlb_id="MLB1",
        title=title,
        price=50,
        commission_pct=15,
        category_path=(root, "MLB9") if root else (),
        permalink="https://x",
        original_price=100,
        affiliate_link="https://meli.la/x",
    )


@pytest.mark.parametrize(
    "title, root, topic",
    [
        ("Perfume Árabe Sabah 100ml Feminino", "MLB1246", "perfume"),
        ("Paleta de Sombras 18 Cores", "MLB1246", "maquiagem"),
        ("Hidratante Corporal CeraVe 473ml", "MLB1246", "cuidados"),
        ("Bolsa Feminina Couro", "MLB1430", "moda"),
        ("Jogo De Panelas Cerâmica 10 Peças", "MLB1574", "cozinha"),
        ("Air Fryer Philco 11L", "MLB5726", "cozinha"),
        ("Aspirador de Pó WAP 1400W", "MLB5726", "eletro"),
        ("Jogo De Lençol 400 Fios Queen", "MLB1574", "casa"),
        ("Panela de Pressão 4,2L", None, "cozinha"),
        ("Cadeira Gamer", None, None),
    ],
)
def test_topic_of(title, root, topic):
    assert topic_of(offer(title, root)) == topic


def test_every_topic_file_renders():
    values = caption_values(offer("Perfume X", "MLB1246"))
    for path in (TEMPLATES / "mulher").glob("*.txt"):
        templates = load_templates(TEMPLATES, "mulher", path.stem)
        assert len(templates) >= 5, path.name
        for t in templates:
            assert "https://meli.la/x" in fill(t, values)
