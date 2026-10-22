import shutil
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ofertinhas import db
from ofertinhas.cloud.backend import WEBHOOK_HEADER, CloudBackend, is_dry_run
from ofertinhas.cloud.cards import R2CardHost, R2Cards

from .test_webhook import FakeBot, message

ROOT = Path(__file__).parents[2]
TOKEN = "tok"
SECRET = "segredo-do-webhook"
H = {"X-Ofertinhas-Token": TOKEN}


class FakeBucket:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key, data, content_type):
        self.objects[key] = (data, content_type)

    async def get(self, key):
        found = self.objects.get(key)
        return found[0] if found else None


@pytest.fixture
def bundle(tmp_path):
    shutil.copy(ROOT / "config.example.yaml", tmp_path / "config.yaml")
    shutil.copytree(ROOT / "templates" / "text", tmp_path / "templates")
    return tmp_path


@pytest.fixture
def backend(bundle):
    clock = {"now": datetime(2026, 10, 22, 15, 0, tzinfo=UTC)}
    env = {"EXTENSION_TOKEN": TOKEN, "TELEGRAM_BOT_TOKEN": "1:x", "ADMIN_CHAT_ID": "777",
           "TELEGRAM_WEBHOOK_SECRET": SECRET, "R2_PUBLIC_URL": "https://pub.r2.dev"}
    conn = db.connect(":memory:")
    b = CloudBackend(env, conn, FakeBucket(), bundle, httpx.AsyncClient(),
                     clock=lambda: clock["now"], bot=FakeBot())
    b.clock_state = clock
    yield b
    conn.close()


def test_dry_run_is_the_default():
    assert is_dry_run({}) and is_dry_run({"DRY_RUN": "true"})
    assert not is_dry_run({"DRY_RUN": "false"})


def test_extension_api_keeps_the_token(backend):
    client = TestClient(backend.app)
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers=H).json()["ok"] is True
    assert client.get("/ext/config", headers=H).json()["categories"]


def test_webhook_needs_secret_in_path_and_header(backend):
    client = TestClient(backend.app)
    update = {"update_id": 1, "message": message("/stats")}
    assert client.post("/tg/errado", json=update, headers={WEBHOOK_HEADER: SECRET}).status_code \
        == 404
    assert client.post(f"/tg/{SECRET}", json=update).status_code == 404
    response = client.post(f"/tg/{SECRET}", json=update, headers={WEBHOOK_HEADER: SECRET})
    assert response.json() == {"ok": True}
    assert backend.bot.send_message.await_args.kwargs["text"] == "Nenhum post enviado hoje."


def test_import_needs_token_and_skips_duplicates(backend):
    client = TestClient(backend.app)
    rows = {"posts": [{"id": 1, "mlb_id": "MLB1", "niche": "casa", "channel": "telegram",
                       "chat": "-100", "status": "sent", "sent_at": "2026-10-22T12:00:00+00:00"}]}
    assert client.post("/admin/import", json=rows).status_code == 401
    assert client.post("/admin/import", json=rows, headers=H).json() == {
        "imported": {"offers": 0, "candidates": 0, "posts": 1, "settings": 0}}
    assert client.post("/admin/import", json=rows, headers=H).json()["imported"]["posts"] == 0
    assert db.posts_today(backend.conn, "-100", backend.clock()) == 1


async def test_tick_runs_minute_jobs_and_expire_every_15_min(backend):
    assert await backend.tick() == ["expire", "publish", "stock_alert", "notify_pending"]
    backend.clock_state["now"] = datetime(2026, 10, 22, 15, 7, tzinfo=UTC)
    assert await backend.tick() == ["publish", "notify_pending"]


async def test_status_shows_the_last_tick(backend):
    await backend.tick()
    status = TestClient(backend.app).get("/admin/status", headers=H).json()
    assert status["dry_run"] is True
    assert status["last_tick"]["at"] == "2026-10-22T15:00:00+00:00"
    assert status["last_tick"]["ran"] == ["expire", "publish", "stock_alert",
                                          "notify_pending"]


def test_post_now_needs_token_and_waits_for_a_running_publish(backend):
    client = TestClient(backend.app)
    assert client.post("/admin/post-now").status_code == 401
    assert client.post("/admin/post-now", headers=H).json() == {"dry_run": True, "posted": []}
    backend._running.add("publish")
    assert client.post("/admin/post-now", headers=H).status_code == 409


def test_import_replaces_a_cloud_decision_with_the_local_cooldown(backend):
    from ofertinhas.cloud.history import import_rows
    from ofertinhas.models import Candidate, CandidateState, Offer

    now = backend.clock()
    db.upsert_offer(backend.conn, Offer(mlb_id="MLB1", title="x", price=10, commission_pct=20,
                                        category_path=(), permalink="https://x"), now=now)
    db.save_candidate(backend.conn, Candidate(mlb_id="MLB1", niche="casa",
                                              state=CandidateState.RENDERED, score=50,
                                              breakdown={}, ref_price=10, decided_at=now))
    local = dict(mlb_id="MLB1", niche="casa", state="posted", score=50, breakdown_json="{}",
                 ref_price=10, decided_at=now.isoformat())
    import_rows(backend.conn, {"candidates": [local]})
    assert db.get_candidate(backend.conn, "MLB1", "casa").state is CandidateState.POSTED


async def test_tick_skips_a_job_still_running(backend):
    backend._running.add("publish")
    assert "publish" not in await backend.tick()


async def test_r2_cards_round_trip_and_public_url():
    bucket = FakeBucket()
    ref = await R2Cards(bucket).save("MLB1-casa.png", b"png")
    assert ref == "cards/MLB1-casa.png"
    assert await R2Cards(bucket).load(ref) == b"png"
    with pytest.raises(FileNotFoundError):
        await R2Cards(bucket).load("cards/nada.png")
    url = await R2CardHost(bucket, "https://pub.r2.dev/").upload(ref, b"png")
    assert url == "https://pub.r2.dev/cards/MLB1-casa.png"


def test_history_export_brings_cooldown_offers_and_recent_posts(backend):
    from ofertinhas.cloud.history import export_rows, import_rows
    from ofertinhas.models import Candidate, CandidateState, Offer

    now = backend.clock()
    local = db.connect(":memory:")
    for mlb, state in (("MLB1", CandidateState.POSTED), ("MLB2", CandidateState.PENDING)):
        db.upsert_offer(local, Offer(mlb_id=mlb, title="x", price=10, commission_pct=20,
                                     category_path=(), permalink="https://x"), now=now)
        db.save_candidate(local, Candidate(mlb_id=mlb, niche="casa", state=state, score=50,
                                           breakdown={}, ref_price=10, decided_at=now))
    db.record_post(local, mlb_id="MLB1", niche="casa", channel="telegram", chat="-100",
                   status="sent", sent_at=now, price=10)
    db.set_niche_override(local, "casa", "paused", True)
    db.set_setting(local, "alert:x", "não vai")
    data = export_rows(local, now)
    assert [o["mlb_id"] for o in data["offers"]] == ["MLB1"]
    assert import_rows(backend.conn, data) == {"offers": 1, "candidates": 1, "posts": 1,
                                               "settings": 1}
    assert db.niche_overrides(backend.conn, "casa") == {"paused": True}
    assert db.get_candidate(backend.conn, "MLB1", "casa").state is CandidateState.POSTED
    local.close()


def test_post_x_needs_the_keys(backend):
    client = TestClient(backend.app)
    assert client.post("/admin/post-x").status_code == 401
    assert client.post("/admin/post-x", headers=H).status_code == 409
