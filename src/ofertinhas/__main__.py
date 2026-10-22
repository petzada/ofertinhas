import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ofertinhas",
        description="Coleta, ranqueia e dispara ofertas de afiliado do Mercado Livre.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="roda o bot e o agendador")
    run.add_argument(
        "--dry-run", action="store_true", help="envia tudo só para o chat do admin"
    )
    sub.add_parser("collect-once", help="coleta uma vez e imprime o ranking")
    sub.add_parser("login-check", help="verifica se a sessão do Mercado Livre está ativa")

    capture = sub.add_parser("capture", help="salva páginas reais como fixtures de teste")
    capture.add_argument("target", choices=["portal", "product"])
    capture.add_argument("url", nargs="?")

    sample = sub.add_parser("render-sample", help="gera uma imagem de exemplo do nicho")
    sample.add_argument("niche")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "capture":
        if args.target == "product" and not args.url:
            parser.error("capture product precisa da URL do produto")
        return _capture(args.target, args.url)
    print(f"Comando '{args.command}' ainda não implementado.", file=sys.stderr)
    return 2


def _capture(target: str, url: str | None) -> int:
    import asyncio

    from . import settings
    from .capture import run_capture
    from .models import TZ, utcnow

    stamp = utcnow().astimezone(TZ).strftime("%Y%m%d-%H%M%S")
    out = settings.data_dir() / "capture" / f"{stamp}-{target}"
    print(
        "Abrindo o navegador. Faça login se pedir e navegue pelas telas que importam.\n"
        "Quando terminar, feche a janela do navegador.\n"
        f"Gravando em {out}"
    )
    rec = asyncio.run(
        run_capture(url or settings.portal_url(), out, settings.chrome_profile_dir())
    )
    print(f"Captura encerrada: {rec.responses} respostas JSON e {rec.pages} snapshots.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
