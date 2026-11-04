# Ofertinhas — regras para agentes

Python 3.12+ (`src/ofertinhas`), extensão de navegador (`extension/`) e o Worker Python da Cloudflare
(`cloud/worker`, Durable Object com SQLite). Operação em `docs/operacao.md`.

## Onde cada coisa roda

| Camada | O que roda | Escopo |
| --- | --- | --- |
| **pre-commit** (lefthook) | `ruff format` + `ruff check --fix` nos arquivos em stage | staged |
| **pre-push** (lefthook) | `pytest --testmon` (só o que o diff afeta) e os testes da extensão | diff |
| **CI** (`ci.yml`) | `ruff check .` em todo PR; matriz 3.12/3.13 + extensão quando o PR fica pronto | repositório |
| **Deploy** (`deploy.yml`) | `cloud/worker/deploy.py` em push na `main` | Worker `ofertinhas` |

- Gates leves onde o agente está (notebook ou VM da nuvem); o pesado fica no CI. Não aumente o pre-push.
- **A coleta roda só no PC** (Brave + extensão): o Mercado Livre bloqueia navegador automatizado. Nada disso
  vai para a nuvem nem para o CI.
- `config.yaml` e `.env` ficam fora do Git e nunca vão para o ambiente da nuvem. Os testes usam mocks; para
  rodar algo que leia config use `config.example.yaml`.
- Sem banco local e sem Docker local. O banco da nuvem é o SQLite do Durable Object; o do PC é separado.

## Fluxo de git — obrigatório

1. Branch nova a partir da `main` atualizada: `<tipo>/<nome-kebab>` (`feat`, `fix`, `chore`, `docs`, `test`,
   `refactor`, `ci`). Nunca commitar direto na `main`.
2. Commits semânticos: `<tipo>(<escopo>): <descrição no imperativo>`.
3. **Fluxo de git (dev solo; mesmo de `~/.claude/CLAUDE.md`):** ao terminar uma implementação, commit +
   push da branch da feature, automático (sem PR não há custo de CI relevante). **"Finaliza"** = PR e
   pronto na sequência, acompanhar o CI, corrigir num push só e avisar. **"Suba pra produção" / "faça o
   merge"** = squash merge e acompanhar o deploy. Draft só se pedido; merge só com esse pedido.
4. Nunca `--no-verify`, nunca desligar hooks, nunca force-push em branch compartilhada.
5. `deploy.py`, `push_secrets.py`, `set_webhook.py` e qualquer `wrangler` com a conta real são ações do
   responsável ou do workflow `deploy.yml`, nunca do agente.

### PR na VM da nuvem (Claude Code na web, app ou thread de projeto)

Na nuvem o proxy do GitHub bloqueia GraphQL, então `gh pr …` e `gh issue …` dão 403. `git push` e
`gh api` (REST) funcionam. O fluxo é o mesmo, pela API REST:

- **"Finaliza":** abrir o PR já pronto (`draft=false`):
  `gh api repos/{owner}/{repo}/pulls -f title='<tipo>(<escopo>): …' -f head=<branch> -f base=main -f body='…' -F draft=false`.
- **"Suba pra produção":** `gh api -X PUT repos/{owner}/{repo}/pulls/<n>/merge -f merge_method=squash`.
- Listar ou ver PR: `gh api repos/{owner}/{repo}/pulls?head={owner}:<branch>`.
- Não coloque `GH_TOKEN` no ambiente da nuvem: não resolve o 403 e deixa o token legível.
