"""Prova: o card do Ofertinhas renderizado num Python Worker (Pillow + qrcode + Poppins)."""

import io
import time

from PIL import Image
from workers import Response, WorkerEntrypoint, fetch

from card import render_card, upgrade_image_url
from models import Offer
from themes import theme_for

PHOTO = "https://http2.mlstatic.com/D_NQ_NP_2X_651621-MLA117648908194_102026-F.webp"


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        t0 = time.perf_counter()
        photo = await fetch(upgrade_image_url(PHOTO))
        product = Image.open(io.BytesIO(await photo.bytes()))
        t1 = time.perf_counter()
        offer = Offer(
            mlb_id="MLB4690740873", title="Bomba De Ar De Mão Pneu Car Air Pump Sem Fio 150 Psi",
            price=78.98, original_price=157.98, commission_pct=66, category_path=("MLB1276",),
            permalink="https://x", pix_only=True, affiliate_link="https://meli.la/1aWWv7B",
        )
        png = render_card(offer, theme_for("esporte", "Ofertas 2KAI"), product)
        t2 = time.perf_counter()
        return Response(png, headers={
            "content-type": "image/png",
            "x-photo-ms": f"{(t1 - t0) * 1000:.0f}",
            "x-render-ms": f"{(t2 - t1) * 1000:.0f}",
        })
