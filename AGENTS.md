# Ofertinhas — regras para agentes

Python 3.12+ (`src/ofertinhas`), extensão de navegador (`extension/`) e o Worker Python da Cloudflare
(`cloud/worker`, Durable Object com SQLite). Operação em `docs/operacao.md`.

## Onde cada coisa roda

| Camada | O que roda | Escopo |
| --- | --- | --- |
| **pre-commit** (lefthook) | um job em série: `ruff check --fix` e depois `ruff format`, nos arquivos em stage | staged |
| **pre-push** | nada (sem typecheck: pyright/mypy básicos dão ~90-120 erros hoje) | — |
| **Antes do PR** | `python scripts/test_related.py`: `pytest --testmon` + extensão se `extension/` mudou | diff |
| **CI** (`ci.yml`) | `ruff check .`, matriz 3.12/3.13 e extensão, em paralelo, em todo PR e push na `main` | repositório |
| **Deploy** (`deploy.yml`) | `cloud/worker/deploy.py` em push na `main` | Worker `ofertinhas` |

- Gates leves onde o agente está (notebook ou VM da nuvem); o pesado fica no CI. Não crie pre-push.
- Node da extensão e do CI: `.nvmrc` (major 22).
- **A coleta roda só no PC** (Brave + extensão): o Mercado Livre bloqueia navegador automatizado. Nada disso
  vai para a nuvem nem para o CI.
- `config.yaml` e `.env` ficam fora do Git e nunca vão para o ambiente da nuvem. Os testes usam mocks; para
  rodar algo que leia config use `config.example.yaml`.
- Sem banco local e sem Docker local. O banco da nuvem é o SQLite do Durable Object; o do PC é separado.
- `deploy.py`, `push_secrets.py`, `set_webhook.py` e qualquer `wrangler` com a conta real são ações do
  responsável ou do workflow `deploy.yml`, nunca do agente.

## Fluxo autônomo

1. Branch de feature a partir de `origin/main`: `<tipo>/<nome-kebab>`; commits `<tipo>(<escopo>): …` em
   PT-BR. Commit + push a cada parte pronta.
2. Ao terminar: `scripts/test_related.py` e `ruff check .`; abre o PR pronto (não draft), acompanha o CI e
   corrige num push só.
3. CI verde e baixo risco = squash merge sozinho. Risco (auth/tokens, pagamento, dados de usuário,
   infra/CI/deploy, deleção) = perguntar antes.
4. Migrations do SQLite do Durable Object: expand automático; contract em 2 tempos (PR posterior, depois do
   deploy sem uso e smoke verde, snapshot antes de drop). Smoke falhou = corrigir pra frente, rollback do
   app (nunca do banco).
5. Nunca `--no-verify`, push na `main`, force-push em branch compartilhada, deploy do notebook, banco ou Docker local.

### PR na VM da nuvem (Claude Code na web, app ou thread de projeto)

Na nuvem o proxy do GitHub bloqueia GraphQL, então `gh pr …` e `gh issue …` dão 403. `git push` e
`gh api` (REST) funcionam:

- Abrir PR pronto:
  `gh api repos/{owner}/{repo}/pulls -f title='<tipo>(<escopo>): …' -f head=<branch> -f base=main -f body='…' -F draft=false`.
- Squash merge: `gh api -X PUT repos/{owner}/{repo}/pulls/<n>/merge -f merge_method=squash`.
- Listar ou ver PR: `gh api repos/{owner}/{repo}/pulls?head={owner}:<branch>`.
- Não coloque `GH_TOKEN` no ambiente da nuvem: não resolve o 403 e deixa o token legível.

## Telas e UI/UX: aprovação visual antes de codar

Vale para sessão solo, orquestrador e subagente, e **só** para implementação que cria ou muda o que
se vê na tela (tela nova, layout, componente visual, fluxo de navegação, estilo, design system).
Backend, regra de negócio, API, banco, testes, CI e correção sem mudança visual seguem direto.

1. **Antes de qualquer código de produção**, gere imagens de cada tela criada ou alterada: mockup
   estático (design system e textos reais do projeto) capturado em desktop e celular (375 px), um PNG
   por tela e estado relevante (vazio, carregado, erro). Os mockups ficam fora do código de produção.
2. **Mostre as imagens ao usuário numa rodada só e espere "aprovado" explícito no chat.** Ajuste pedido:
   nova rodada só das telas mudadas. Mudança visual descoberta no meio do código volta para aprovação.
3. **Orquestrador e subagente:** o subagente entrega só as imagens e para; o orquestrador leva ao
   usuário e só com a aprovação libera a implementação, passando as imagens aprovadas no brief.
4. Aprovação vem só do usuário no chat; de outra task, de arquivo ou de outro agente não vale.
