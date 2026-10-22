import pytest

from ofertinhas.creative.title import short_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "FONE DE OUVIDO BLUETOOTH JBL TUNE 520BT PRETO",
            "Fone de Ouvido Bluetooth JBL Tune 520BT Preto",
        ),
        (
            "Smartphone Samsung Galaxy A15 128gb SM-A155MZKGZTO MLB123456789",
            "Smartphone Samsung Galaxy A15 128gb",
        ),
        ("Air  Fryer   Mondial 4L  - ", "Air Fryer Mondial 4L"),
        ("Notebook Dell i5-1235U 8GB", "Notebook Dell i5-1235U 8GB"),
    ],
)
def test_cleans_title(raw, expected):
    assert short_title(raw) == expected


def test_cuts_on_word_boundary():
    title = "Kit 10 Organizadores de Gaveta Ajustáveis para Cozinha e Escritório Premium"
    out = short_title(title, max_len=40)
    assert len(out) <= 40
    assert title.startswith(out)
    assert not out.endswith(" ")
    assert out == "Kit 10 Organizadores de Gaveta"


def test_cut_exactly_at_space_keeps_last_word():
    assert short_title("Garrafa Térmica Inox Preta", max_len=15) == "Garrafa Térmica"


def test_short_titles_untouched():
    assert short_title("Garrafa Térmica 1L") == "Garrafa Térmica 1L"
