from ofertinhas.text import slugify


def test_slugify_strips_accents_and_symbols():
    assert slugify("Link falhou: MLB1 — Ação!") == "link-falhou-mlb1-acao"


def test_slugify_empty():
    assert slugify("!!!") == ""
