from datetime import time
from pathlib import Path

import pytest
import yaml

from ofertinhas.config import AppConfig, ConfigError, load_config, load_config_text

EXAMPLE = Path(__file__).parents[1] / "config.example.yaml"

MINIMAL = """
defaults:
  weights:
    commission_pct: 35
niches:
  casa:
    categories: [MLB1574]
    weights: {discount_pct: 35}
    telegram_chat_id: -1001
"""


def test_example_config_loads():
    cfg = load_config(EXAMPLE)
    assert cfg.niche_names()


def test_niche_merges_partial_weights_over_defaults():
    casa = load_config_text(MINIMAL).for_niche("casa")
    assert casa.weights.discount_pct == 35
    assert casa.weights.commission_pct == 35
    assert casa.weights.full == 7  # default do modelo


def test_template_defaults_to_niche_name():
    assert load_config_text(MINIMAL).for_niche("casa").template == "casa"


def test_override_wins_over_yaml():
    casa = load_config_text(MINIMAL).for_niche(
        "casa", overrides={"auto_approve_at": 90, "weights": {"discount_pct": 10}}
    )
    assert casa.auto_approve_at == 90
    assert casa.weights.discount_pct == 10
    assert casa.weights.commission_pct == 35


def test_thresholds_must_be_ordered():
    text = MINIMAL.replace("telegram_chat_id", "auto_approve_at: 50\n    telegram_chat_id")
    with pytest.raises(ConfigError, match="casa"):
        load_config_text(text)


def test_unknown_key_is_rejected():
    with pytest.raises(ConfigError, match="comission_pct"):
        load_config_text(MINIMAL.replace("discount_pct: 35", "comission_pct: 35"))


def test_niche_needs_a_channel():
    with pytest.raises(ConfigError, match="canal"):
        load_config_text(MINIMAL.replace("telegram_chat_id: -1001", "keywords: [x]"))


def test_niche_needs_categories_or_keywords():
    with pytest.raises(ConfigError, match="categories"):
        load_config_text(MINIMAL.replace("categories: [MLB1574]", "template: casa"))


def test_unquoted_window_hour_gives_hint():
    # YAML 1.1 lê 23:00 sem aspas como número sexagesimal (1380).
    data = yaml.safe_load(MINIMAL)
    data["defaults"]["pacing"] = {"window": ["08:00", 1380]}
    with pytest.raises(ConfigError, match="aspas"):
        AppConfig.from_dict(data)


def test_window_parses_times():
    casa = load_config_text(MINIMAL).for_niche("casa")
    assert casa.pacing.window == (time(8, 0), time(23, 0))


def test_override_is_validated():
    cfg = load_config_text(MINIMAL)
    with pytest.raises(ConfigError):
        cfg.for_niche("casa", overrides={"manual_review_at": 95})


@pytest.mark.parametrize("bad", ["Casa", "casa:2", "nome-de-nicho-muito-comprido", "c a"])
def test_niche_name_format(bad):
    with pytest.raises(ConfigError, match="nome do nicho"):
        load_config_text(MINIMAL.replace("  casa:", f"  {bad!r}:"))


def test_unknown_niche():
    with pytest.raises(KeyError):
        load_config_text(MINIMAL).for_niche("pets")
