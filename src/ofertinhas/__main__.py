import argparse
import sys


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
    sub.add_parser("new-token", help="gera o token que a extensão usa para falar com o backend")
    sub.add_parser("whatsapp-groups", help="lista os grupos e JIDs da instância da WhatsMiau.dev")
    sample = sub.add_parser("render-sample", help="gera uma imagem de exemplo do nicho")
    sample.add_argument("niche")
    sub.add_parser("install-task", help="inicia o backend ao fazer logon no Windows")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"Comando '{args.command}' ainda não implementado.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
