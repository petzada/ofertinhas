from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofertinhas import db
from ofertinhas.config import load_config
from ofertinhas.run import make_jobs

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
ROOT = Path(__file__).parents[1]


@pytest.fixture
def ctx(tmp_path):
    conn = db.connect(tmp_path / "ofertinhas.db")
    yield SimpleNamespace(
        conn=conn,
        cfg=load_config(ROOT / "config.example.yaml"),
        data_dir=tmp_path,
        templates_dir=ROOT / "templates" / "text",
        bot=SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock()),
        telegram=SimpleNamespace(send_photo=AsyncMock(return_value="1"),
                                 send_message=AsyncMock(return_value="9"),
                                 edit_message=AsyncMock(), pin_message=AsyncMock()),
        fetch_image=AsyncMock(return_value=None),
        notify=AsyncMock(),
    )
    conn.close()


def jobs(ctx, dry_run=True):
    return make_jobs(
        conn=ctx.conn, cfg=ctx.cfg, data_dir=ctx.data_dir, templates_dir=ctx.templates_dir,
        bot=ctx.bot, telegram=ctx.telegram, fetch_image=ctx.fetch_image, notify=ctx.notify,
        admin_chat_id=777, dry_run=dry_run, clock=lambda: NOW,
    )


def test_every_job_is_in_the_shared_schedule(ctx):
    from ofertinhas.jobs import SCHEDULE

    assert set(jobs(ctx)) == set(SCHEDULE)


async def test_jobs_run_on_an_empty_database(ctx):
    for job in jobs(ctx).values():
        await job()
    ctx.telegram.send_photo.assert_not_awaited()
    assert list((ctx.data_dir / "backups").glob("*.db"))
    ctx.telegram.pin_message.assert_awaited_once_with(777, "9")  # status fixado


async def test_run_refuses_while_the_cloud_has_the_webhook(tmp_path):
    import httpx
    import respx

    from ofertinhas.run import CloudActive, run
    from ofertinhas.settings import Settings

    settings = Settings.from_env({"OFERTINHAS_DATA_DIR": str(tmp_path),
                                  "TELEGRAM_BOT_TOKEN": "1:x", "ADMIN_CHAT_ID": "1"})
    with respx.mock:
        respx.get("https://api.telegram.org/bot1:x/getWebhookInfo").mock(
            return_value=httpx.Response(200, json={"ok": True, "result": {
                "url": "https://ofertinhas.example.workers.dev/tg/s"}}))
        with pytest.raises(CloudActive):
            await run(settings, load_config(ROOT / "config.example.yaml"), dry_run=True)
    assert not (tmp_path / "ofertinhas.db").exists()  # nem chegou a abrir o banco
