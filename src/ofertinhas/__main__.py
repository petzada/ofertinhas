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
    print(f"Comando '{args.command}' ainda não implementado.", file=sys.stderr)
    return 2


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
