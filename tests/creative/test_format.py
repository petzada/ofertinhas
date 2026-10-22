from ofertinhas.creative.format import to_telegram_html, to_whatsapp, visible_length

LINK = "https://mercadolivre.com/sec/a_b~c"


def test_whatsapp_keeps_neutral_markup():
    text = "*Oferta* ~R$ 10~"
    assert to_whatsapp(text) == text


def test_telegram_converts_bold_and_strike():
    html = to_telegram_html("De ~R$ 10,00~ por *R$ 5,00*")
    assert html == "De <s>R$ 10,00</s> por <b>R$ 5,00</b>"


def test_telegram_escapes_html_in_text():
    assert to_telegram_html("Kit <3 & amigos") == "Kit &lt;3 &amp; amigos"


def test_telegram_leaves_links_alone():
    assert to_telegram_html(f"👉 {LINK}") == f"👉 {LINK}"


def test_markup_does_not_cross_lines():
    assert to_telegram_html("a *b\nc* d") == "a *b\nc* d"


def test_visible_length_ignores_tags_and_entities():
    assert visible_length("<b>ab</b> &amp;") == 4
