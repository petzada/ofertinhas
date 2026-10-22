"""Entrada do Worker "ofertinhas": liga o runtime da Cloudflare ao `ofertinhas.cloud`.

O Worker só repassa ao Durable Object (um único, "main") as rotas públicas e, de minuto em
minuto, o Cron. Toda a lógica e o banco ficam no Durable Object, que atende uma coisa por vez
entre um `await` e outro.
"""

import logging
from pathlib import Path
from urllib.parse import urlparse

import js
from pyodide.ffi import create_proxy, to_js
from workers import DurableObject, Response, WorkerEntrypoint, asgi

# O pacote é importado no primeiro request (`_backend`): o Worker proíbe aleatoriedade na
# inicialização, e httpx/PTB/FastAPI a usam ao serem importados.

BUNDLE = Path(__file__).parent / "bundle"
PUBLIC_PREFIXES = ("/health", "/ext/", "/tg/", "/admin/")
CRON_URL = "https://ofertinhas.internal/_cron"
ENV_NAMES = (
    "EXTENSION_TOKEN", "EXTENSION_ORIGIN", "TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID",
    "ML_AFFILIATE_TAG", "WHATSMIAU_API_KEY", "WHATSMIAU_INSTANCE", "WHATSMIAU_BASE_URL",
    "R2_PUBLIC_URL", "TELEGRAM_WEBHOOK_SECRET", "DRY_RUN",
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # não logar URLs com o token do bot


class JsBucket:
    """O binding R2 com bytes do Python, na interface que `ofertinhas.cloud.cards` espera."""

    def __init__(self, binding):
        self.binding = binding

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        options = to_js({"httpMetadata": {"contentType": content_type}},
                        dict_converter=js.Object.fromEntries)
        await self.binding.put(key, to_js(data), options)

    async def get(self, key: str) -> bytes | None:
        obj = await self.binding.get(key)
        if obj is None:
            return None
        data = await obj.arrayBuffer()
        return data.to_bytes() if hasattr(data, "to_bytes") else bytes(data)


def _env_values(env) -> dict[str, str]:
    values = {}
    for name in ENV_NAMES:
        value = getattr(env, name, None)
        if value is not None:
            values[name] = str(value)
    return values


class Ofertinhas(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env
        self.backend = None

    def _exec(self, sql: str, *params):
        cursor = self.ctx.storage.sql.exec(sql, *params)
        rows = cursor.raw().toArray()
        return list(cursor.columnNames), rows.to_py() if hasattr(rows, "to_py") else rows

    def _transaction(self, fn):
        proxy = create_proxy(fn)
        try:
            return self.ctx.storage.transactionSync(proxy)
        finally:
            proxy.destroy()

    def _backend(self):
        if self.backend is None:
            import httpx

            from ofertinhas import db
            from ofertinhas.cloud.backend import CloudBackend
            from ofertinhas.cloud.sqlstore import DOConnection
            from ofertinhas.creative import image

            image.FONTS_DIR = BUNDLE / "fonts"  # no bundle, as fontes não ficam em assets/
            conn = DOConnection(self._exec, self._transaction)
            db.migrate(conn)
            self.backend = CloudBackend(_env_values(self.env), conn, JsBucket(self.env.CARDS),
                                        BUNDLE, httpx.AsyncClient())
        return self.backend

    async def fetch(self, request):
        backend = self._backend()
        if urlparse(request.url).path == "/_cron":
            return Response.json({"ran": await backend.tick()})
        return await asgi.fetch(backend.app, request, self.env)


class Default(WorkerEntrypoint):
    def _stub(self):
        return self.env.STATE.get(self.env.STATE.idFromName("main"))

    async def fetch(self, request):
        if not urlparse(request.url).path.startswith(PUBLIC_PREFIXES):
            return Response("não encontrado", status=404)
        return await self._stub().fetch(request)

    async def scheduled(self, controller, env, ctx):
        await self._stub().fetch(CRON_URL)
