from ofertinhas.config import load_config_text
from ofertinhas.models import Offer
from ofertinhas.ranking.niches import match_niches

CFG = load_config_text(
    """
niches:
  casa:
    categories: [MLB1574]
    keywords: [airfryer]
    telegram_chat_id: -1
  tech:
    categories: [MLB1000]
    keywords: [fone bluetooth, airfryer smart]
    telegram_chat_id: -2
  pets:
    keywords: [ração]
    telegram_chat_id: -3
"""
)


def offer(title="Produto", path=("MLB9999",)) -> Offer:
    return Offer(
        mlb_id="MLB1", title=title, price=100.0, commission_pct=10.0,
        category_path=path, permalink="https://x",
    )


def niches_of(o):
    return match_niches(o, [CFG.for_niche(n) for n in CFG.niche_names()])


def test_match_by_ancestor_category():
    assert niches_of(offer(path=("MLB1574", "MLB5726", "MLB123"))) == ["casa"]


def test_match_by_keyword_ignoring_accents():
    assert niches_of(offer(title="Racao Golden 15kg")) == ["pets"]


def test_category_match_takes_precedence_over_keywords():
    o = offer(title="Fone Bluetooth com estojo", path=("MLB1574", "MLB55"))
    assert niches_of(o) == ["casa"]


def test_multiple_keyword_matches_keep_config_order():
    assert niches_of(offer(title="Airfryer Smart Wi-Fi")) == ["casa", "tech"]


def test_no_match():
    assert niches_of(offer(title="Caneta azul")) == []


def test_keyword_needs_whole_words():
    assert niches_of(offer(title="Fones bluetoothx")) == []


def test_search_term_routes_offers_without_category():
    cfg = load_config_text("""
niches:
  casa:
    categories: [MLB1574]
    telegram_chat_id: -1
  noivas:
    categories: [MLB1574]
    search_terms: [Jogo de Cama, mala de viagem]
    whatsapp_group_jid: "1@g.us"
""")
    niches = [cfg.for_niche(n) for n in cfg.niche_names()]
    found = offer(title="Kit Lençol Queen 4 Peças", path=())
    assert match_niches(found, niches, search="jogo de cama") == ["noivas"]
    assert match_niches(found, niches, search="  JOGO  de cáma") == ["noivas"]  # normalizado
    assert match_niches(found, niches, search="panela") == []
    assert match_niches(found, niches) == []
    # categoria conhecida: casa e noivas por categoria, sem repetir pelo termo
    known = offer(path=("MLB1574",))
    assert match_niches(known, niches, search="mala de viagem") == ["casa", "noivas"]
