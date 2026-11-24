# Ofertinhas

Python 3.12+ (`src/ofertinhas`), extensão de navegador (`extension/`) e o Worker Python da Cloudflare
(`cloud/worker`, Durable Object com SQLite). Operação em `docs/operacao.md`.

## Comandos

- Instalar: `python -m pip install -e ".[dev]"`; configurar: `python -m ofertinhas setup`.
- Lint e formatação: `ruff check .` e `ruff format`.
- Testes afetados pelo diff: `python scripts/test_related.py` (`pytest --testmon` + extensão se `extension/` mudou).
- CI (`ci.yml`): `ruff check .`, matriz 3.12/3.13 e extensão. Deploy (`deploy.yml`): `cloud/worker/deploy.py`
  em push na `main` (Worker `ofertinhas`).
- Node da extensão e do CI: `.nvmrc` (major 22).

## Fatos do projeto

- **A coleta roda só no PC** (Brave + extensão): o Mercado Livre bloqueia navegador automatizado. Nada disso
  vai para a nuvem nem para o CI.
- `config.yaml` e `.env` ficam fora do Git. Os testes usam mocks; para rodar algo que leia config use
  `config.example.yaml`.
- O banco da nuvem é o SQLite do Durable Object; o do PC é separado.
- `deploy.py`, `push_secrets.py`, `set_webhook.py` e `wrangler` com a conta real mexem em produção.
- Migrations do SQLite do Durable Object: expand primeiro; contract (drop/rename) só num PR posterior, depois
  do deploy sem uso.
