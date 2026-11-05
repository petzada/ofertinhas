"""Lojas de onde vêm as ofertas. A origem sai do prefixo do ID (a coluna continua `mlb_id`):
sem prefixo é Mercado Livre, `AMZ-<ASIN>` é Amazon e `SHP-<itemId>` é Shopee. O ID nunca leva
`:`, que separa os campos no callback dos botões do bot.
"""

ML, AMAZON, SHOPEE = "ml", "amazon", "shopee"
PREFIXES = {AMAZON: "AMZ-", SHOPEE: "SHP-"}
LABELS = {ML: "Mercado Livre", AMAZON: "Amazon", SHOPEE: "Shopee"}


def source_of(offer_id: str) -> str:
    for source, prefix in PREFIXES.items():
        if offer_id.startswith(prefix):
            return source
    return ML


def make_id(source: str, native_id: str | int) -> str:
    native = str(native_id)
    if ":" in native:
        raise ValueError(f"ID com ':' quebra os botões do bot: {native}")
    return PREFIXES[source] + native if source in PREFIXES else native


def label(offer_id: str) -> str:
    return LABELS[source_of(offer_id)]
