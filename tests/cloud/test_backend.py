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
ADMIN = {"X-Ofertinhas-Admin": "adm"}


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
    env = {"EXTENSION_TOKEN": TOKEN, "ADMIN_TOKEN": "adm", "TELEGRAM_BOT_TOKEN": "1:x",
           "ADMIN_CHAT_ID": "777",
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
    assert client.post("/admin/import", json=rows, headers=ADMIN).json() == {
        "imported": {"offers": 0, "candidates": 0, "posts": 1, "settings": 0}}
    imported = client.post("/admin/import", json=rows, headers=ADMIN).json()["imported"]
    assert imported["posts"] == 0
    assert db.posts_today(backend.conn, "-100", backend.clock()) == 1


async def test_tick_runs_minute_jobs_and_expire_every_15_min(backend):
    assert await backend.tick() == ["expire", "publish", "stock_alert", "notify_pending"]
    backend.clock_state["now"] = datetime(2026, 10, 22, 15, 7, tzinfo=UTC)
    assert await backend.tick() == ["publish", "notify_pending"]


async def test_status_shows_the_last_tick(backend):
    await backend.tick()
    status = TestClient(backend.app).get("/admin/status", headers=ADMIN).json()
    assert status["dry_run"] is True
    assert status["last_tick"]["at"] == "2026-10-22T15:00:00+00:00"
    assert status["last_tick"]["ran"] == ["expire", "publish", "stock_alert",
                                          "notify_pending"]


def test_post_now_needs_token_and_waits_for_a_running_publish(backend):
    client = TestClient(backend.app)
    assert client.post("/admin/post-now").status_code == 401
    assert client.post("/admin/post-now", headers=H).status_code == 401  # token da extensão
    assert client.post("/admin/post-now", headers=ADMIN).json() == {
        "dry_run": True, "posted": []}
    backend._running.add("publish")
    assert client.post("/admin/post-now", headers=ADMIN).status_code == 409


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
    assert client.post("/admin/post-x", headers=ADMIN).status_code == 409


def test_stats_reports_the_day(backend):
    stats = TestClient(backend.app).get("/admin/stats", headers=ADMIN).json()
    assert stats["offers_seen_today"] == 0 and stats["links_by_hour"] == []
    assert TestClient(backend.app).get("/admin/stats").status_code == 401


def test_admin_routes_are_closed_without_admin_token(bundle):
    env = {"EXTENSION_TOKEN": TOKEN, "TELEGRAM_BOT_TOKEN": "1:x", "ADMIN_CHAT_ID": "777"}
    conn = db.connect(":memory:")
    b = CloudBackend(env, conn, FakeBucket(), bundle, httpx.AsyncClient(), bot=FakeBot())
    client = TestClient(b.app)
    assert client.get("/admin/status", headers=H).status_code == 401
    assert client.get("/admin/status", headers={"X-Ofertinhas-Admin": ""}).status_code == 401
    conn.close()


async def test_tick_pins_the_status_and_prunes_at_their_times(backend):
    from unittest.mock import AsyncMock

    backend.telegram.send_message = AsyncMock(return_value="50")
    backend.telegram.pin_message = AsyncMock()
    backend.clock_state["now"] = datetime(2026, 10, 22, 11, 0, tzinfo=UTC)  # 08:00 em SP
    assert "status" in await backend.tick()
    backend.telegram.pin_message.assert_awaited_once_with(777, "50")
    backend.clock_state["now"] = datetime(2026, 10, 22, 7, 30, tzinfo=UTC)  # 04:30 em SP
    ran = await backend.tick()
    assert "prune" in ran and "backup" not in ran


def test_build_info_comes_from_the_bundle(bundle):
    (bundle / "version.json").write_text('{"commit": "abc1234def", "dirty": false, '
                                         '"config_sha": "1a2b3c4d5e6f"}', encoding="utf-8")
    env = {"EXTENSION_TOKEN": TOKEN, "ADMIN_TOKEN": "adm", "TELEGRAM_BOT_TOKEN": "1:x",
           "ADMIN_CHAT_ID": "777"}
    conn = db.connect(":memory:")
    b = CloudBackend(env, conn, FakeBucket(), bundle, httpx.AsyncClient(), bot=FakeBot())
    client = TestClient(b.app)
    assert client.get("/health", headers=H).json()["build"]["commit"] == "abc1234def"
    assert client.get("/admin/status", headers=ADMIN).json()["build"]["config_sha"] \
        == "1a2b3c4d5e6f"
    conn.close()


def test_niche_preview_tests_a_new_niche_before_deploy(backend):
    client = TestClient(backend.app)
    db.upsert_offer(backend.conn, db_offer("MLB1", "Jogo de Cama Casal 4 Peças"),
                    now=backend.clock_state["now"])
    body = {"niche": "noivas", "days": 1,
            "config": {"categories": ["MLB1574"], "filters": {"required_keywords": ["jogo*"]}}}
    assert client.post("/admin/niche-preview", json=body, headers=H).status_code == 401
    report = client.post("/admin/niche-preview", json=body, headers=ADMIN).json()
    assert report["matched"] == 1 and report["matched_sample"][0]["title"].startswith("Jogo")
    unknown = client.post("/admin/niche-preview", json={"niche": "nada"}, headers=ADMIN)
    assert unknown.status_code == 404
    bad = {"niche": "x", "config": {"categories": ["MLB0"]}}
    assert client.post("/admin/niche-preview", json=bad, headers=ADMIN).status_code == 422


def db_offer(mlb_id, title):
    from ofertinhas.models import Offer

    return Offer(mlb_id=mlb_id, title=title, price=50, original_price=100, commission_pct=25,
                 category_path=("MLB1574",), permalink="https://x")


INVITE_1 = "https://chat.whatsapp.com/AbCdEfGhIjKlMn01"
INVITE_2 = "https://chat.whatsapp.com/AbCdEfGhIjKlMn02"
NOIVAS = {"groups": [{"invite": INVITE_1, "jid": "1@g.us"}, {"invite": INVITE_2, "jid": "2@g.us"}]}


def test_group_link_redirects_and_counts_clicks_by_source(backend):
    client = TestClient(backend.app, follow_redirects=False)
    assert client.get("/g/noivas").status_code == 404  # ainda sem grupo cadastrado
    client.put("/admin/groups/noivas", json=NOIVAS, headers=ADMIN)
    response = client.get("/g/noivas?utm_source=TikTok&utm_campaign=bf26")
    assert response.status_code == 302 and response.headers["location"] == INVITE_1
    assert response.headers["cache-control"] == "no-store"
    client.get("/g/noivas?utm_source=tiktok&utm_campaign=bf26")
    client.get("/g/noivas")
    client.get("/g/noivas?utm_source=maria%40gmail.com")  # texto livre não entra
    client.get("/g/noivas?utm_source=11999998888")
    client.head("/g/noivas?utm_source=tiktok")  # pré-visualização: redireciona sem contar
    client.get("/g/noivas?utm_source=pinterest", headers={"User-Agent": "Pinterestbot/1.0"})
    client.get("/g/noivas?utm_source=pinterest",
               headers={"User-Agent": "Mozilla/5.0 [Pinterest/Android]"})
    assert client.get("/admin/clicks").status_code == 401
    report = client.get("/admin/clicks", headers=ADMIN).json()
    assert report["since"] == "2026-09-23"
    assert {(r["source"], r["campaign"], r["clicks"]) for r in report["by_day"]} == {
        ("tiktok", "bf26", 2), ("direto", "-", 1), ("outro", "-", 2), ("pinterest", "-", 1)}
    assert {r["day"] for r in report["by_day"]} == {"2026-10-22"}
    assert report["by_source"][0] == {"niche": "noivas", "source": "tiktok", "clicks": 2}
    assert client.get("/admin/clicks?niche=casa", headers=ADMIN).json()["by_day"] == []


def test_admin_groups_validates_and_switches_by_hand(backend):
    client = TestClient(backend.app, follow_redirects=False)
    assert client.put("/admin/groups/noivas", json=NOIVAS).status_code == 401
    bad = {"groups": [{"invite": "https://golpe.com/x"}]}
    assert client.put("/admin/groups/noivas", json=bad, headers=ADMIN).status_code == 422
    assert client.put("/admin/groups/Noivas!", json=NOIVAS, headers=ADMIN).status_code == 422
    assert client.put("/admin/groups/noivas", json=NOIVAS, headers=ADMIN).json()["active"] == 0
    assert client.post("/admin/groups/noivas/next", headers=ADMIN).json()["active"] == 1
    assert client.get("/g/noivas").headers["location"] == INVITE_2
    client.post("/admin/groups/noivas/next", headers=ADMIN)  # todos lotados: fica no último
    assert client.get("/g/noivas").headers["location"] == INVITE_2
    listed = client.get("/admin/groups", headers=ADMIN).json()
    assert listed["noivas"]["active"] == 1 and listed["noivas"]["groups"][0]["full"] is True
    reopened = {"groups": [{"invite": INVITE_1, "full": False}, {"invite": INVITE_2}]}
    assert client.put("/admin/groups/noivas", json=reopened, headers=ADMIN).json()["active"] == 0
    assert client.post("/admin/groups/casa/next", headers=ADMIN).status_code == 404


async def test_group_members_moves_to_the_next_group_when_full(backend):
    from unittest.mock import AsyncMock, MagicMock

    TestClient(backend.app).put("/admin/groups/noivas", json=NOIVAS, headers=ADMIN)
    backend.notify = AsyncMock()
    backend.whatsapp = MagicMock()
    backend.whatsapp.list_groups = AsyncMock(return_value=[
        {"id": "1@g.us", "participants": [{"id": str(i)} for i in range(1000)]},
        {"id": "2@g.us", "size": 12}, {"id": "outro@g.us", "size": 5}])
    assert await backend._group_members() == {"1@g.us": 1000, "2@g.us": 12}
    backend.whatsapp.list_groups.assert_awaited_once_with(participants=True)
    assert "agora leva ao grupo 2 de 2" in backend.notify.await_args.args[0]
    groups = TestClient(backend.app).get("/admin/groups", headers=ADMIN).json()["noivas"]
    assert groups["active"] == 1 and groups["groups"][1]["members"] == 12
    backend.whatsapp.list_groups.return_value[1]["size"] = 1010
    await backend._group_members()
    assert "Todos os grupos" in backend.notify.await_args.args[0]
    backend.notify.reset_mock()
    await backend._group_members()  # o aviso de "todos lotados" sai no máximo a cada 12 h
    backend.notify.assert_not_awaited()


async def test_tick_checks_group_members_only_with_whatsapp(bundle):
    env = {"EXTENSION_TOKEN": TOKEN, "TELEGRAM_BOT_TOKEN": "1:x", "ADMIN_CHAT_ID": "777",
           "WHATSMIAU_API_KEY": "k", "WHATSMIAU_INSTANCE": "i"}
    conn = db.connect(":memory:")
    b = CloudBackend(env, conn, FakeBucket(), bundle, httpx.AsyncClient(), bot=FakeBot(),
                     clock=lambda: datetime(2026, 10, 22, 15, 0, tzinfo=UTC))
    assert (await b.tick())[-1] == "group_members"  # sem grupo com jid, nem chama a API
    conn.close()
