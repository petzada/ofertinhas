"""Página de entrada no grupo do WhatsApp (`/grupo` do Worker), destino dos anúncios da Meta.

O HTML sai pronto no build (`cloud/worker/build.py`), a partir de `templates/landing/grupo.html`
e do bloco `landing` do config. O Worker só devolve o arquivo, sem acordar o Durable Object.
Com `pixel_id`, a página carrega o Pixel da Meta (PageView) e manda `Lead` no clique do botão,
que é o evento de conversão da campanha.
"""

import html
import json
from pathlib import Path

from .config import LandingConfig

TEMPLATE = Path("landing") / "grupo.html"

WA_ICON = (
    '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M12 2a10 10 0 0 '
    "0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2"
    "-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2"
    "-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5"
    "a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 2.3.8 "
    '3.2.6.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2-.1-.1-.3-.2-.5-.3Z"/></svg>'
)

PIXEL = """<script>
!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init','{pixel_id}');fbq('track','PageView');
</script>"""


NOSCRIPT = (
    '<noscript><img height="1" width="1" style="display:none" alt="" '
    'src="https://www.facebook.com/tr?id={pixel_id}&amp;ev=PageView&amp;noscript=1"></noscript>'
)


TELEGRAM_BANNER = """  <section class="tg">
    <h2>Quer ofertas de tudo? ✈️</h2>
    <p>No nosso grupo do Telegram tem achadinho de tecnologia, casa, pet, esporte, infantil
      e muito mais, o dia todo.</p>
    <a id="cta-tg" href="{url}" rel="noopener">Entrar no grupo do Telegram</a>
  </section>
  <script>document.getElementById('cta-tg').addEventListener('click', function(){{
    if (window.fbq) fbq('trackCustom', 'TelegramClick');
  }});</script>"""


def render(template: str, landing: LandingConfig) -> str:
    pixel = landing.pixel_id
    telegram = landing.telegram_url
    return (
        template.replace("{{PIXEL_HEAD}}", PIXEL.replace("{pixel_id}", pixel) if pixel else "")
        .replace("{{PIXEL_NOSCRIPT}}", NOSCRIPT.replace("{pixel_id}", pixel) if pixel else "")
        .replace(
            "{{PIXEL_NOTE}}", " Usamos o Pixel da Meta para medir os anúncios." if pixel else ""
        )
        .replace("{{GROUP_URL_JSON}}", json.dumps(landing.group_url))
        .replace("{{GROUP_URL}}", html.escape(landing.group_url))
        .replace("{{NAME}}", html.escape(landing.name))
        .replace("{{WA_ICON}}", WA_ICON)
        .replace(
            "{{TELEGRAM_BANNER}}",
            TELEGRAM_BANNER.format(url=html.escape(telegram)) if telegram else "",
        )
    )


def build_page(templates_dir: Path, landing: LandingConfig | None) -> str | None:
    """O HTML pronto da página, ou None quando o config não tem `landing`."""
    if landing is None:
        return None
    return render((templates_dir / TEMPLATE).read_text(encoding="utf-8"), landing)
