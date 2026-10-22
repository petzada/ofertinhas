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
        telegram=SimpleNamespace(send_photo=AsyncMock(return_value="1")),
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


def test_every_scheduled_job_exists(ctx):
    assert set(jobs(ctx)) == {"notify_pending", "render", "publish", "expire", "backup"}


async def test_jobs_run_on_an_empty_database(ctx):
    for job in jobs(ctx).values():
        await job()
    ctx.telegram.send_photo.assert_not_awaited()
    assert list((ctx.data_dir / "backups").glob("*.db"))
