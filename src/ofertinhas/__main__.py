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
    args = build_parser().parse_args(argv)
    print(f"Comando '{args.command}' ainda não implementado.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
