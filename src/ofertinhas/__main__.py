import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ofertinhas",
        description="Ranqueia e dispara ofertas de afiliado do Mercado Livre.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="roda a API da extensão, o bot e o agendador")
    run.add_argument(
        "--dry-run", action="store_true", help="envia tudo só para os destinos de teste"
    )
    setup = sub.add_parser("setup", help="cria config.yaml, .env e a config da extensão")
    setup.add_argument("--tag", help="sua etiqueta de afiliado do Mercado Livre")
    sub.add_parser("api", help="roda só a API local da extensão (avisos saem no terminal)")
    sub.add_parser("new-token", help="gera o token que a extensão usa para falar com o backend")
    sub.add_parser("whatsapp-groups", help="lista os grupos e JIDs da instância da WhatsMiau.dev")
    sample = sub.add_parser("render-sample", help="gera uma imagem de exemplo do nicho")
    sample.add_argument("niche")
    sub.add_parser("install-task", help="inicia o backend ao fazer logon no Windows")

    har = sub.add_parser("har-extract", help="gera fixtures sem dados sensíveis a partir de um HAR")
    har.add_argument("har_path", type=Path)
    har.add_argument("--out", type=Path, default=Path("tests/fixtures/portal"))
    har.add_argument(
        "--mask", action="append", default=[], metavar="TEXTO=SUBSTITUTO",
        help="troca um texto pessoal (ex.: seu nome) em todos os corpos; pode repetir",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "har-extract":
        return _har_extract(parser, args)
    if args.command == "new-token":
        return _new_token()
    if args.command == "api":
        return _api()
    if args.command == "setup":
        from .setup import run_setup

        for line in run_setup(Path.cwd(), args.tag):
            print(f"- {line}")
        return 0
    if args.command == "render-sample":
        return _render_sample(args.niche)
    print(f"Comando '{args.command}' ainda não implementado.", file=sys.stderr)
    return 2


def _api() -> int:
    from . import db
    from .api.app import ApiState, create_app
    from .config import ConfigError, load_config
    from .settings import Settings, SettingsError

    try:
        settings = Settings.load()
        settings.require("EXTENSION_TOKEN")
        if not settings.config_path.exists():
            raise ConfigError(
                f"não achei {settings.config_path.name}: copie config.example.yaml para "
                "config.yaml e ajuste os nichos"
            )
        cfg = load_config(settings.config_path)
    except (SettingsError, ConfigError) as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1

    import uvicorn

    settings.data_dir.mkdir(parents=True, exist_ok=True)

    async def notify(text: str) -> None:
        print(f"[aviso ao admin] {text}", flush=True)

    state = ApiState(
        settings=settings,
        conn=db.connect(settings.data_dir / "ofertinhas.db"),
        cfg=cfg,
        notify=notify,
    )
    print(f"API local em http://127.0.0.1:{settings.api_port} (Ctrl+C para parar)")
    uvicorn.run(create_app(state), host="127.0.0.1", port=settings.api_port, log_level="info")
    return 0


def _render_sample(niche: str) -> int:
    from PIL import Image, ImageDraw

    from .creative.image import render_card
    from .creative.themes import theme_for
    from .models import Offer
    from .settings import Settings

    product = Image.new("RGB", (600, 600), "#F2F2F2")
    draw = ImageDraw.Draw(product)
    draw.rounded_rectangle((150, 120, 450, 520), radius=60, fill="#2B2B2B")
    draw.ellipse((220, 200, 380, 360), fill="#5A5A5A")
    offer = Offer(
        mlb_id="MLB000000000",
        title="Fritadeira Elétrica Air Fryer Mondial 4L Preta com Timer",
        price=299.90,
        original_price=499.90,
        commission_pct=12,
        category_path=("MLB1574",),
        permalink="https://produto.mercadolivre.com.br/MLB-000000000",
        free_shipping=True,
        full=True,
        affiliate_link="https://mercadolivre.com/sec/1AbC2dE",
    )
    out = Settings.load().data_dir / "samples" / f"{niche}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(render_card(offer, theme_for(niche), product))
    print(f"Exemplo gravado em {out}")
    return 0


def _new_token() -> int:
    from .settings import new_token

    token = new_token()
    print(
        f"EXTENSION_TOKEN={token}\n\n"
        "1. Cole a linha acima no arquivo .env do projeto.\n"
        "2. Cole o mesmo token nas opções da extensão no Brave."
    )
    return 0


def _har_extract(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    from .har import extract_har

    masks = {}
    for item in args.mask:
        old, sep, new = item.partition("=")
        if not sep or not old:
            parser.error(f"--mask precisa ser TEXTO=SUBSTITUTO: {item!r}")
        masks[old] = new
    files = extract_har(args.har_path, args.out, masks)
    print(f"{len(files)} fixtures gravadas em {args.out} (veja {args.out / 'index.md'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
