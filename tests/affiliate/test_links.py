import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ofertinhas import db
from ofertinhas.affiliate.links import (
    LinkError,
    apply_link_result,
    build_create_link_body,
    next_link_request,
    parse_create_link_response,
)
from ofertinhas.models import Candidate, CandidateState, Offer

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
S = CandidateState
FIXTURE = Path(__file__).parents[1] / "fixtures" / "portal" / "create-link.json"
PERMALINK = ("https://www.mercadolivre.com.br/carregador-duplo-kingster-compativel-controles-"
             "ps5-com-led-indicador-bivolt-base-dock-e-cabo-tipo-c/p/MLB53879960")


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def offer(mlb_id="MLB5790540954", **kw):
    base = dict(mlb_id=mlb_id, title="Carregador", price=50, commission_pct=12,
                category_path=("MLB1144",), permalink=PERMALINK, extra_commission=True,
                collected_at=NOW)
    base.update(kw)
    return Offer(**base)


def seed(conn, mlb_id="MLB5790540954", niche="casa", state=S.APPROVED, score=80.0, **kw):
    if db.get_offer(conn, mlb_id) is None:
        db.upsert_offer(conn, offer(mlb_id, **kw), now=NOW)
    db.save_candidate(conn, Candidate(mlb_id=mlb_id, niche=niche, state=state, score=score,
                                      breakdown={}, ref_price=50, decided_at=NOW))


def fixture_response():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]["body"]


def test_body_matches_what_the_portal_sends():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["request"]["body"]
    assert build_create_link_body(offer(), "minhatag") == expected


def test_parse_real_response():
    short, code = parse_create_link_response(offer(), fixture_response())
    assert short == "https://meli.la/33zyUam" and code == "QL81M2-HWKB"


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(total_error=1),
    lambda r: r.update(urls=[]),
    lambda r: r["urls"][0].update(short_url="https://evil.example/x"),
    lambda r: r["urls"][0].update(origin_url="www.mercadolivre.com.br/outro/p/MLB1"),
])
def test_parse_rejects_bad_responses(mutate):
    response = fixture_response()
    mutate(response)
    with pytest.raises(LinkError):
        parse_create_link_response(offer(), response)


def test_next_request_picks_best_approved_without_link(conn):
    seed(conn, "MLB1", score=70)
    seed(conn, "MLB2", score=90)
    seed(conn, "MLB3", score=99, state=S.PENDING)
    req = next_link_request(conn, "minhatag", NOW)
    assert req["mlb_id"] == "MLB2"
    assert req["body"]["tag"] == "minhatag"
    assert req["url"].endswith("/affiliate-program/api/v2/affiliates/createLink")


def test_requested_offer_waits_ten_minutes(conn):
    seed(conn, "MLB1")
    assert next_link_request(conn, "t", NOW)["mlb_id"] == "MLB1"
    assert next_link_request(conn, "t", NOW + timedelta(minutes=5)) is None
    assert next_link_request(conn, "t", NOW + timedelta(minutes=11))["mlb_id"] == "MLB1"


def test_offer_with_link_is_promoted_without_request(conn):
    seed(conn, "MLB1", niche="casa", state=S.LINKED)
    seed(conn, "MLB1", niche="tech", state=S.APPROVED)
    db.set_affiliate_link(conn, "MLB1", "https://meli.la/x")
    assert next_link_request(conn, "t", NOW) is None
    assert db.get_candidate(conn, "MLB1", "tech").state is S.LINKED


def test_apply_success_links_every_approved_niche(conn):
    seed(conn, niche="casa")
    seed(conn, niche="tech")
    failed = apply_link_result(conn, "MLB5790540954", fixture_response(), None)
    assert failed is False
    stored = db.get_offer(conn, "MLB5790540954")
    assert stored.affiliate_link == "https://meli.la/33zyUam"
    assert stored.search_code == "QL81M2-HWKB"
    assert {c.state for c in db.candidates_for_offer(conn, "MLB5790540954")} == {S.LINKED}


def test_apply_failures_until_link_failed(conn):
    seed(conn)
    assert apply_link_result(conn, "MLB5790540954", None, "HTTP 500") is False
    assert apply_link_result(conn, "MLB5790540954", {"total_error": 1, "urls": []}, None) is False
    assert apply_link_result(conn, "MLB5790540954", None, "timeout") is True
    assert db.get_candidate(conn, "MLB5790540954", "casa").state is S.LINK_FAILED


def test_apply_unknown_offer(conn):
    with pytest.raises(LinkError):
        apply_link_result(conn, "MLB404", None, "x")
