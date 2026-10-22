# Handoff — migração do Ofertinhas para a Cloudflare (22/10/2026, ~04h)

Documento para a próxima sessão continuar sem reler a conversa anterior.
Projeto: `C:\Users\Marcio\Desktop\ofertinhas` (Git, branch `main`, último commit `366230d`).

---

## 00. Virada feita: a nuvem está em produção (22/10, ~04h45)

- **Modo:** `DRY_RUN = "false"`. O `run` local foi parado, o webhook do bot aponta para o
  Worker (`set_webhook.py`) e a extensão usa a nuvem (`backendUrl` no
  `extension/config.local.json`).
- **Histórico:** importado com `import_history.py` (40 decisões em cooldown, 14 posts e os
  ajustes do bot). Na importação, as decisões locais substituem as da nuvem.
- **Post de verificação:** saiu às 07:41 UTC nos dois grupos oficiais pelo
  `POST /admin/post-now`, um post avulso que ignora janela e intervalo uma vez.
- **Acompanhamento:** `GET /admin/status`, com token, mostra o último tick do Cron, as contagens
  por estado e os últimos posts por canal.
- **Teste do WhatsApp:** com `DRY_RUN = "true"`, o WhatsApp vai só para `WHATSAPP_TEST_JID`
  (conversa do próprio número), nunca para o grupo.
- **Regra confirmada pelo usuário:** automática com desconto > 39% e comissão > 20%.
- **Depende do PC:** coleta e links continuam na extensão do Brave. O
  `python -m ofertinhas keep-awake` impede o Windows de suspender; a etapa 3 (Agendador
  abrindo o Brave) ainda falta, assim como a 4 (mensagem fixada) e a 5 (apagar o
  `ofertinhas-spike-card` e atualizar a spec e o plano).
- **Para voltar ao PC:** `python set_webhook.py --delete`, `backendUrl` de volta para
  `http://127.0.0.1:8765` e `python -m ofertinhas run`.

## 0. Etapa 2 implantada em dry-run (22/10, madrugada)

- **Banco escolhido:** SQLite do Durable Object (o usuário escolheu).
- **Worker `ofertinhas`** publicado em `https://ofertinhas.marciopetigrosso.workers.dev`, com
  `DRY_RUN = "true"` no `wrangler.toml`, Cron `* * * * *`, binding R2 `CARDS` e os segredos
  do `.env` já enviados (`cloud/worker/push_secrets.py`, que também criou o
  `TELEGRAM_WEBHOOK_SECRET` no `.env`).
- `/health` e `/ext/*` respondem com o token e recusam sem ele.
- **Como ficou o código:**
  - `cloud/worker/` tem `build.py` (copia o pacote, fontes, modelos e `config.yaml` para
    `src/`), `src/entry.py` (Worker e Durable Object), `wrangler.toml` e os scripts da virada:
    `push_secrets.py`, `import_history.py` e `set_webhook.py`.
  - `src/ofertinhas/cloud/` tem `sqlstore.py` (adaptador com cara de `sqlite3`), `cards.py`
    (R2), `webhook.py` (updates da PTB para os handlers de sempre), `backend.py` (FastAPI +
    jobs + `tick`) e `history.py`.
  - Refatorações no pacote: `jobs.py` (`make_jobs` e `guarded`), `cardstore.py` (cards em
    disco ou R2) e `dotenv` importado só no PC.
- **O que a sondagem mostrou no Pyodide:** httpx (GET e multipart), PTB, FastAPI (por
  `workers.asgi`), pydantic e yaml funcionam. `PRAGMA user_version` e `BEGIN` são recusados
  (por isso a tabela `_meta` e o `transactionSync`). `.ttf` e `.yaml` só entram no bundle com
  `[[rules]]`. Imports que usam aleatoriedade não podem rodar na inicialização.
- **Falta:** a virada (seção 4.3). Os scripts estão prontos. O histórico vai com
  `import_history.py` depois de parar o `run` local.

## 1. Onde paramos em uma frase

A **prova do card num Python Worker passou** (Pillow + qrcode + Poppins rodando no Pyodide, card idêntico ao local).
O próximo passo é a **etapa 2: portar o backend para a Cloudflare**. Nada da etapa 2 foi escrito ainda.

O usuário aprovou com: *"Eu já pago o Workers de 5$, então mete marcha nesse modelo recomendado. Faça a prova antes de migrar tudo."*
A prova está feita, então dá para seguir sem nova aprovação. Antes de codar, só a **pergunta da seção 4.1** precisa de resposta.

---

## 2. Estado atual do sistema (produção local)

- O `python -m ofertinhas run` está rodando em **modo real** na aba de terminal **c10** do app.
  - Jobs ativos: `notify_pending`, `render`, `publish`, `expire` e `backup` (4h).
  - **Deixar rodando até a nuvem assumir.** Desligar só na etapa 5.
- A extensão no Brave do usuário coleta e gera links apontando para o backend local (`extension/config.local.json`).
- Ponta a ponta validada com posts reais:
  - Telegram: grupo **Ofertas 2KAI** (`@ofertas2kai`, chat `-1004330132499`).
  - WhatsApp: grupo **Achadinhos das Noivas ❤️** (`120363413394029296@g.us`), via WhatsMiau, com o card hospedado no R2.
- Testes: 329 em Python (`pytest`) e 46 na extensão (`node --test`), todos verdes no `366230d`.
- Árvore limpa no Git, **exceto os arquivos novos desta passagem** (não commitados):
  - `cloud/spike-card/` (fontes da prova);
  - este documento.

---

## 3. A prova (etapa 1) — concluída

**Fontes:** copiados para `cloud/spike-card/`. Os gerados estão no `.gitignore`.

| Arquivo | Papel |
|---|---|
| `build_spike.py` | Copia `image.py`, `themes.py`, `title.py`, `models.py` e `brl` do pacote; embute as fontes em base64 em `src/fonts.py`; remove `httpx` e `fetch_product_image`. Rode antes do deploy. |
| `src/entry.py` | `class Default(WorkerEntrypoint)`: baixa a foto com `workers.fetch`, chama `render_card` e devolve o PNG. |
| `pyproject.toml` / `pylock.toml` | Dependências `pillow`, `qrcode`, `tzdata`; grupo dev com `workers-py` e `workers-runtime-sdk`. |
| `wrangler.toml` | `python_workers`, `compatibility_date = "2026-10-15"`. |
| `card-da-nuvem.png` | O card que o Worker devolveu. |

**Publicado em:** `https://ofertinhas-spike-card.marciopetigrosso.workers.dev`. Apagar depois; é só prova.

**Resultados:**
- HTTP 200, PNG de 229 KB.
- Pacote de 4,7 MB (1,5 MB comprimido).
- Inicialização de 754 ms no deploy; primeira chamada a frio em ~3,2 s; as seguintes em ~0,7 s.
- O QR decodifica para `https://meli.la/1aWWv7B`.
- O `perf_counter` mostra 0 ms de render porque o relógio do Worker só anda durante I/O. Não é bug.
- A foto é de um guarda-sol porque o id de imagem foi fixado a partir do HAR. Também não é bug.

**Como fazer o deploy (Windows, PowerShell 5.1):**
```powershell
cd C:\Users\Marcio\Desktop\ofertinhas\cloud\spike-card
$env:PATH = "C:\Users\Marcio\Desktop\ofertinhas\.venv\Scripts;" + $env:PATH   # o uv está no .venv
python build_spike.py
uvx --from workers-py pywrangler deploy
```
- O Wrangler 4.151.3 já está autenticado na conta do usuário.
- O `uv` resolve o Python 3.14 gerenciado (`cpython-3.14.9`). Não é preciso `UV_PYTHON_PREFERENCE`.
- **Armadilha já resolvida:** o uv tinha deixado um shim quebrado em `C:\Users\Marcio\.local\bin\python3.14.exe` e ele foi removido. Se `pywrangler` reclamar do Python de novo, procure esse shim primeiro.

---

## 4. Etapa 2 — backend no Worker (próximo trabalho)

### 4.1 Decisão em aberto: D1 ou SQLite do Durable Object

O plano aprovado dizia **D1**. Durante a pesquisa surgiu uma alternativa que parece melhor, mas **ainda não foi apresentada ao usuário**. Apresente e deixe o usuário escolher antes de codar.

- **D1:** o acesso é assíncrono (`await env.DB.prepare(...).bind(...).all()`). Isso obriga a reescrever todo o `db.py` e os chamadores, que hoje usam `sqlite3` síncrono (`conn.execute`, `with conn:`).
- **SQLite de Durable Object (Python):**
  - `ctx.storage.sql.exec(sql, *params)` é **síncrono**, então um adaptador fino com cara de `sqlite3.Connection` reaproveita o `db.py` e as migrações por `PRAGMA user_version` quase sem mudança;
  - um único DO (`idFromName("main")`) serializa tudo, sem corrida entre cron, webhook e extensão;
  - tem **alarms**, o que dá agendamento fino;
  - tem PITR de 30 dias;
  - ressalvas: `exec` não aceita `BEGIN` ou `SAVEPOINT` (use `ctx.storage.transaction_sync`), e convém testar se o `PRAGMA user_version` funciona ali.
- **Recomendação:** DO com SQLite, com o Worker de entrada repassando `fetch`, `scheduled` e o webhook para o DO.
- Configuração no `wrangler.toml`:
  ```toml
  [[durable_objects.bindings]]
  name = "STATE"
  class_name = "Ofertinhas"

  [[migrations]]
  tag = "v1"
  new_sqlite_classes = ["Ofertinhas"]
  ```

### 4.2 O que portar e como

| Hoje (local) | Na nuvem |
|---|---|
| FastAPI `/ext/*` e `/health` (`api/app.py`) | Roteamento no `fetch` do Worker, **mesmas rotas e mesmo `EXTENSION_TOKEN`**, para a extensão só trocar o `backendUrl`. |
| APScheduler (`scheduler.py`, `run.make_jobs`) | Cron Trigger `* * * * *` mais despacho por minuto (render, publish, notify_pending, expire a cada 15 min, backup diário, status 3x por dia), ou alarms do DO. A regra de ritmo continua no `publish_due`: das 8h às 23h, 25 min entre posts, até 25 por dia. |
| python-telegram-bot (polling) | **Webhook**: `setWebhook` apontando para `/tg/<segredo>`, validando `X-Telegram-Bot-Api-Secret-Token`. Tratar os callbacks de aprovar e recusar e os comandos à mão, com chamadas diretas à Bot API. A PTB não entra no Worker. |
| `httpx.AsyncClient` (`TelegramSender`, `WhatsAppSender`, `CardHost`, `fetch_product_image`) | **httpx não funciona no Worker.** Criar um adaptador mínimo sobre `workers.fetch` com a mesma interface que esses senders usam (`post`, `get`, `.json()`, `.status_code`, `.content`), para os módulos não mudarem. |
| `CardHost` (S3 com SigV4) | **Binding R2** (`[[r2_buckets]] binding = "CARDS", bucket_name = "ofertinhas-cards"`) com `await env.CARDS.put(key, png)`. A URL pública continua sendo `R2_PUBLIC_URL/cards/{mlb}-{niche}.png`. |
| Cards em disco (`data/cards/*.png`) | Gerar o PNG e enviar na hora (ou guardar no R2). Não há disco persistente. |
| `config.yaml` + `.env` | Config embutida no bundle (YAML convertido em JSON no build) e segredos via `wrangler secret put`. Overrides do banco continuam no banco. |
| `backup.py` (cópia do SQLite) | Dump diário para o R2 (`backups/AAAA-MM-DD.sql`), ou confiar no PITR do DO. |

**Verificar logo no começo:** se `pydantic` v2 e `pyyaml` importam no Pyodide. Ambos devem estar no Pyodide; se não, a config vira JSON mais dataclasses.

**Estratégia de código:**
- Reaproveitar o pacote `src/ofertinhas` (puro Python) num build como o `build_spike.py`, em vez de manter cópia.
- Isolar o que é específico do Worker (entrada, adaptador de fetch, adaptador de SQL, webhook) numa pasta própria, por exemplo `cloud/worker/`.
- Os testes atuais continuam valendo para a lógica.

**Dados:**
- Começar com o **banco zerado**, por pedido do usuário ("zerar a fila e começar do zero").
- Migrar **apenas o histórico de posts** (tabela de posts com `mlb_id`, `niche`, `sent_at`, `price`) para o `repost_cooldown_days` (7 dias) não repostar.

**Segredos para o `wrangler secret put`**, todos já no `.env`:
- `EXTENSION_TOKEN`, `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `ML_AFFILIATE_TAG`;
- `WHATSMIAU_API_KEY`, `WHATSMIAU_INSTANCE`, `R2_PUBLIC_URL`;
- mais um segredo novo para o webhook do Telegram.

Envie por script que lê o `.env` e repassa ao `wrangler secret put` pela stdin, **sem imprimir valores**. Nunca peça para o usuário colar segredo no chat.

### 4.3 Virada (cutover), na ordem

1. Fazer o deploy do Worker em `dry-run` (tudo vai para o chat do admin) e testar `/health` e `/ext/*` com o token.
2. Trocar o `backendUrl` da extensão para a nuvem e incluir `https://*.workers.dev/*` em `host_permissions` no `manifest.json`. O usuário recarrega a extensão.
3. Conferir coleta, links e cards na nuvem em `dry-run`.
4. Parar o `run` local (aba c10) e **só então** chamar `deleteWebhook`/`setWebhook`. Com o webhook ativo, o polling local para de receber updates.
5. Desligar o `dry-run` na nuvem.

---

## 5. Etapas seguintes (já aprovadas)

**3. Extensão rodando sozinha:**
- Agendador do Windows abre o Brave em ~3 horários (7h30, 11h30 e 16h30), com "despertar o computador".
- A extensão coleta ao abrir.
- A nuvem sinaliza "colete agora" quando a fila está baixa (por exemplo, `/ext/config` devolve `collect_now`).
- Opcional: fechar o Brave depois.
- Objetivo: ofertas "quentinhas", coletadas perto do horário de postar.

**4. Mensagem fixada de status** no chat do admin, às 8h, 13h e 20h:
- editar a mesma mensagem fixada, em vez de mandar uma nova;
- conteúdo: fila pronta, posts de hoje (x/25), aprovadas sem link, pendentes, última coleta e estado do WhatsApp (`connection_state`).

**5. Fechamento:**
- desligar o `run` local;
- apagar o Worker `ofertinhas-spike-card` (`npx wrangler delete ofertinhas-spike-card`, que é ação destrutiva e precisa de confirmação);
- atualizar a spec e o plano em `docs/superpowers/`.

---

## 6. Regras de negócio que não podem se perder

- **Decisão por oferta:**
  - desconto **> 39%** e comissão **> 20%** → automática (`strict: true`);
  - desconto **≥ 30%** e comissão **≥ 15%** → card de aprovação;
  - o resto é descartado.
  - Mesma regra para todos os nichos.
- **Fila de envio:**
  - **automáticas primeiro**; aprovadas à mão completam (`_next_in_group` ordena por `notified_at is not None, -score`);
  - os links seguem a mesma prioridade.
- **Cards de aprovação** são só bônus: só aparecem quando o destino não tem fluxo automático (`APPROVED`, `LINKED`, `RENDERED`, `QUEUED`). Lotes de 5.
- **Grupos:** um grupo no Telegram e um no WhatsApp para os 8 nichos. Nichos com o mesmo destino dividem fila e ritmo.
- **Ritmo:** das 08h às 23h, 1 post a cada 25 min sem variação (`jitter_min: 0`), até 25 por dia.
- **Cotas:** 10 automáticas e 8 em revisão por nicho por dia. `max_offer_age_hours` 6. `repost_cooldown_days` 7.
- Coleta e links **sem trava de horário**. Só o envio respeita a janela.
- Frete grátis e Full ficam **fora do ranking** (peso 0).
- **Card:**
  - topo "OFERTAS 2KAI" (de `brand`), sem a categoria;
  - legenda de aprovação enxuta (categoria, nota, nome, preço por, preço de, desconto e comissão);
  - texto e imagem só por template, sem IA.
- **WhatsApp:**
  - a WhatsMiau aceita **só URL pública** em `sendMedia` (base64 e multipart são recusados);
  - mandar `send_presence` antes, com ~4 s de espera;
  - a trava `whatsapp_enabled` está ligada.
- **Mercado Livre:** bloqueia navegador automatizado. A coleta e os links só acontecem pela extensão no Brave real do usuário, já logado. **Não tentar contornar detecção de bot.**

---

## 7. Ambiente e armadilhas

**Regras de carga** (`~/.claude/CLAUDE.md`):
- um subagente por vez;
- subagente que edita usa `isolation: "worktree"`;
- nunca lint e testes juntos;
- localmente, só testes relacionados aos arquivos alterados.

**Ferramentas:**
- Cloudflare: use a **CLI `cf`** para recursos da conta (R2, D1). Em pasta com `wrangler.toml`, use Wrangler/`pywrangler` para dev, build e deploy.
- `cf cli search` não existe na v0.15. Use `--help`.

**PowerShell 5.1:**
- quebra aspas em `python -c` e em mensagens de commit; escreva scripts no scratchpad e evite aspas duplas no `-m`;
- `Set-Content -Encoding utf8` grava BOM; use a ferramenta Write para arquivos de texto.

**Venv e CLI:**
- venv: `.venv` (Python 3.13);
- CLI: `python -m ofertinhas run|api|setup|new-token|recut|telegram-setup|whatsapp-groups|whatsapp-connect|render-sample|har-extract`.

**Segredos:**
- `.env` e `config.yaml` ficam fora do Git e **nunca são exibidos**; leia só por script.
- Conta Cloudflare: `106cf131868ebc0cef16b7905e9d181a`.
- Bucket `ofertinhas-cards`, público em `https://pub-eccd2e49fb534e44b3658cf5b69d2ff1.r2.dev`.

**Documentação de referência:**
- `docs/superpowers/specs/2026-10-21-ofertinhas-design.md`;
- `docs/superpowers/plans/2026-10-21-ofertinhas-plan.md`;
- `docs/notes/portal-mapping.md`;
- `docs/notes/extensao-teste.md`.

---

## 8. Primeira mensagem sugerida para a próxima sessão

> Leia `docs/notes/handoff-2026-10-22-nuvem.md` e siga a etapa 2. Me apresente primeiro a escolha D1 × SQLite do Durable Object (seção 4.1) e depois comece a portar.
