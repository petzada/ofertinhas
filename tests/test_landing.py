"""Página /grupo: HTML pronto no build, com o link do grupo e o Pixel só quando configurado."""

from pathlib import Path

import pytest

from ofertinhas.config import ConfigError, LandingConfig, load_config_text
from ofertinhas.landing import build_page

TEMPLATES = Path(__file__).parents[1] / "templates"
URL = "https://chat.whatsapp.com/AbC123xyz"
BASE = "niches: {casa: {categories: [MLB1574], telegram_chat_id: -1}}\n"


def test_page_has_group_link_and_no_pixel_by_default():
    page = build_page(TEMPLATES, LandingConfig(group_url=URL))
    assert page.count(URL) >= 3 and "{{" not in page
    assert "fbq(" not in page.split("<script>\n(function")[0]  # sem Pixel no <head>
    assert "Grupo VIP de Achadinhos" in page


def test_pixel_tracks_pageview_and_lead_on_click():
    page = build_page(TEMPLATES, LandingConfig(group_url=URL, pixel_id="123456789012345"))
    assert "fbq('init','123456789012345')" in page and "fbq('track','PageView')" in page
    assert "fbq('track', 'Lead')" in page and "Pixel da Meta" in page


def test_no_landing_block_means_no_page():
    assert load_config_text(BASE).landing is None
    assert build_page(TEMPLATES, None) is None


@pytest.mark.parametrize(
    "bad",
    [
        'landing: {group_url: "https://example.com/x"}',
        'landing: {group_url: "' + URL + '", pixel_id: "abc"}',
    ],
)
def test_rejects_bad_landing(bad):
    with pytest.raises(ConfigError):
        load_config_text(BASE + bad)
