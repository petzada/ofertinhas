# Ofertinhas — Plano de implementação

**Spec:** [2026-10-21-ofertinhas-design.md](../specs/2026-10-21-ofertinhas-design.md)
**Data:** 2026-10-21

## Como executar este plano

- **Testes antes do código:** cada tarefa começa pelo teste que falha. Depois vem a implementação mínima até passar e, por fim, um commit (`feat:`, `test:`, `chore:`…).
- **Testes locais:** só os arquivos da tarefa (`pytest tests/<arquivo> -q`). A suíte completa roda no GitHub Actions. Nunca rodar lint e testes ao mesmo tempo.
- **Ambiente local:** Windows, Python 3.13 em venv (`python -m venv .venv`), dependências via `pip install -e ".[dev]"`. Código compatível com Python ≥ 3.12; o Docker do VPS usa a imagem do Playwright com 3.12. Docker não é necessário localmente.
- **Tarefas marcadas 👤 precisam de você:** login no ML, criação do bot, pareamento do WhatsApp, VPS.
- **Critério de pronto de cada tarefa:** testes verdes e commit feito.

## Estrutura alvo

```
ofertinhas/
├── pyproject.toml
├── config.example.yaml
├── .env.example
├── src/ofertinhas/
│   ├── __main__.py          # CLI: run, run --dry-run, collect-once, login-check, capture, render-sample
│   ├── settings.py          # variáveis de ambiente (.env)
│   ├── config.py            # modelos pydantic do config.yaml + merge defaults/nicho/overrides
│   ├── models.py            # Offer, OfferState, Score, Post
│   ├── db.py                # schema, migrações, repositório
│   ├── pipeline.py          # transições de estado (funções puras sobre db)
│   ├── ranking/
│   │   ├── filters.py
│   │   ├── scoring.py
│   │   └── niches.py
│   ├── browser.py           # contexto persistente, lock, pausas humanas, dump de debug
│   ├── collector/
│   │   ├── portal.py        # navegação + interceptação de JSON
│   │   ├── parsers.py       # JSON/HTML → Offer
│   │   └── selectors.py
│   ├── affiliate/
│   │   ├── linkgen.py       # barra do produto + fallback Gerador de link
│   │   └── validate.py      # formato + redirect → MLB
│   ├── creative/
│   │   ├── title.py
│   │   ├── text.py          # templates + sorteio sem repetição
│   │   ├── format.py        # neutro → WhatsApp / Telegram HTML
│   │   └── image/
│   │       ├── base.py
│   │       └── themes.py    # cor/logo/fonte por nicho
│   ├── approval/
│   │   ├── messages.py      # card de aprovação + breakdown da nota
│   │   ├── bot.py           # handlers de callback e edição
│   │   └── commands.py      # /corte /peso /pausar /fila /top /stats /chatid
│   ├── publisher/
│   │   ├── pacing.py        # puro: pode postar agora?
│   │   ├── queue.py         # próxima oferta por grupo + revalidação
│   │   ├── telegram.py
│   │   └── whatsapp.py
│   ├── scheduler.py         # jobs APScheduler + isolamento de erros
│   └── backup.py
├── templates/text/<nicho>.txt
├── assets/fonts/, assets/logos/
├── tests/ (espelha src/) + tests/fixtures/
├── docker/Dockerfile, docker/login-entrypoint.sh
├── docker-compose.yml
├── .github/workflows/ci.yml
└── README.md
```

**Refinamento da spec (login):** o perfil do Chromium não pode ser aberto por dois processos ao mesmo tempo. Por isso o login roda na **mesma imagem** do app, num serviço `login` (profile `login`) com Xvfb, x11vnc e noVNC, e o worker é parado antes. Isso fica num único comando: `make login`, que roda `docker compose stop ofertinhas && docker compose --profile login run --rm --service-ports login`.

---

## Fase 0: Base do projeto

### T0.1 Scaffold
- **Arquivos:** `pyproject.toml`, `.gitignore`, `src/ofertinhas/__init__.py`, `src/ofertinhas/__main__.py` (stub com argparse), `tests/test_smoke.py`.
- **Dependências:** `playwright`, `apscheduler<4`, `python-telegram-bot>=21`, `httpx`, `pillow`, `qrcode`, `pydantic>=2`, `pyyaml`, `python-dotenv`. Dev: `pytest`, `pytest-asyncio`, `respx`, `pyzbar`, `freezegun`, `ruff`.
- **Teste:** `python -m ofertinhas --help` sai com código 0.
- `.gitignore`: `.venv/`, `.env`, `data/`, `__pycache__/`, `*.db`.

### T0.2 CI
- **Arquivo:** `.github/workflows/ci.yml` com dois jobs sequenciais, `ruff check` e depois `pytest`. Instala `libzbar0` para o `pyzbar`.

---

## Fase 1: Núcleo (config, banco, ranking)

### T1.1 Modelos ✅
- **Arquivo:** `models.py`.
- **Feito diferente do previsto:** o produto (`Offer`) ficou separado da decisão por nicho (`Candidate`). Assim o mesmo produto pode estar postado num nicho e pendente em outro, o que deixa o `multi_niche` e o cooldown por nicho corretos.
- `CandidateState` (enum): `pending, approved, rejected, discarded, linked, link_failed, rendered, queued, posted, expired`.
- `Offer`: `mlb_id, title, price, original_price, commission_pct, category_path` (da raiz até a folha; o coletor preenche via API pública de categorias), `permalink, image_url, rating, sold_count, free_shipping, full, collected_at, affiliate_link`.
- `Candidate`: `mlb_id, niche, state, score, breakdown, ref_price, decided_at, caption, card_path, notified_at`.
- Propriedades: `discount_pct` e `commission_brl`.
- **Testes:** `discount_pct` com e sem preço original; `commission_brl` arredondado.

### T1.2 Config
- **Arquivos:** `config.py`, `config.example.yaml`.
- Modelos pydantic: `Weights`, `Caps`, `Filters`, `Pacing`, `NicheConfig`, `AppConfig`.
- `AppConfig.for_niche(name)` faz o deep merge: `defaults` → `niches[name]` → overrides do banco.
- Validação: `manual_review_at < auto_approve_at`, pesos ≥ 0, chat ids presentes, janela `HH:MM`.
- **Testes:** merge parcial de pesos; override vence o YAML; config inválida gera erro legível; o `config.example.yaml` carrega sem erro.

### T1.3 Banco
- **Arquivo:** `db.py` (`sqlite3`, WAL, `PRAGMA user_version` para migrações).
- Tabelas:
  - `offers`, com PK `mlb_id`, histórico de preço em `price_history` e `last_posted_at` por nicho em `posts`.
  - `scores`: `mlb_id, niche, score, breakdown_json`.
  - `posts`: `mlb_id, niche, channel, chat, message_id, sent_at, status, attempts, error`.
  - `settings`: `key, value_json`.
  - `template_usage`: `chat, template_idx, used_at`.
- Funções: `upsert_offer` (atualiza preço, comissão e selos sem regredir o estado), `set_state`, `get_by_state`, `record_post`, `last_post_at(chat)`, `posts_today(chat)`, `get/set_setting`.
- **Testes** (SQLite em memória): o upsert não duplica e preserva o estado; as migrações são idempotentes; as consultas de contagem respeitam o fuso `America/Sao_Paulo`.

### T1.4 Filtros
- **Arquivo:** `ranking/filters.py`. Função `passes(offer, filters) -> (bool, motivo)`.
- **Testes:** preço mínimo e máximo; nota mínima; `require_free_shipping`/`require_full`; keyword bloqueada sem diferenciar maiúsculas e acentos ("Réplica" bate com "replica").

### T1.5 Roteamento de nicho
- **Arquivo:** `ranking/niches.py`. Função `match_niches(offer, cfg) -> list[str]`: primeiro categoria, depois keywords.
- **Testes:** casa por categoria; casa por keyword; nenhum nicho; mais de um nicho.

### T1.6 Nota ✅
- **Arquivo:** `ranking/scoring.py`. Função `score_offer(offer, niche_cfg, now) -> Score`, com breakdown por critério.
- **Feito diferente do previsto:** a normalização usa alvos absolutos (`targets`), e não o lote: `min(v, alvo) / alvo`; `sold_count` em `log1p`; `rating` de `rating_floor` a 5; `freshness` com decaimento linear; booleanos valem 0 ou 1.
- **Testes:**
  - Uma oferta que vence em tudo tira 100.
  - Outlier acima do cap não achata as demais.
  - Lote de uma oferta só não divide por zero.
  - Peso zero ignora o critério.
  - O breakdown soma a nota final.

### T1.7 Pipeline de decisão
- **Arquivo:** `pipeline.py`. Função `score_and_route(db, cfg)`:
  1. Aplica os filtros e o cooldown de repost (`repost_cooldown_days` e queda de preço ≥ `repost_price_drop_pct`).
  2. Calcula a nota em cada nicho e escolhe o melhor (ou todos, com `multi_niche`).
  3. Muda o estado para `approved`, `pending` ou `discarded`.
- **Testes:** cada faixa de nota cai no estado certo; repost bloqueado no cooldown; repost liberado com queda de preço; nicho pausado não recebe oferta.

---

## Fase 2: Navegador e coletor

### T2.1 Navegador
- **Arquivo:** `browser.py`.
- `BrowserSession` (async context manager) com `launch_persistent_context(DATA_DIR/chrome-profile)`, headless no worker e locale `pt-BR`.
- Um `asyncio.Lock` global garante uma aba por vez. `human_pause(min,max)`.
- `dump_debug(page, label)` salva PNG e HTML em `data/debug/<ts>-<label>/`.
- `is_logged_in(page)` detecta o redirecionamento para a tela de login.
- **Testes:** `human_pause` respeita os limites (random com seed); `dump_debug` grava os dois arquivos (página falsa). A parte com navegador real é validada manualmente em T2.2.

### T2.2 👤 Captura de fixtures reais
- **Arquivo:** CLI `python -m ofertinhas capture portal|product <url>`.
- Abre o navegador **visível** com o perfil local (`data/chrome-profile`). Você faz login uma vez no notebook.
- Grava em `tests/fixtures/portal/` todas as respostas JSON da lista de ofertas, mais o HTML final e um HAR, e em `tests/fixtures/product/` a página do produto antes e depois de acionar a barra de afiliado.
- **Saída:** fixtures commitadas, com dados pessoais removidos (nome e e-mail da conta) por um script `scripts/scrub_fixtures.py`, e um resumo em `docs/notes/portal-mapping.md` de onde está cada campo (comissão, preço, frete grátis, Full).
- **Esta tarefa define os detalhes de T2.3 e T3.1.**

### T2.3 Parsers
- **Arquivos:** `collector/parsers.py`, `collector/selectors.py`.
- `parse_portal_json(payload) -> list[Offer]` é a fonte principal; `parse_portal_html(html) -> list[Offer]` é o fallback.
- Normaliza preço (`"R$ 1.299,90"` → `1299.90`), comissão (`"14%"` → `14.0`) e extrai o MLB id do permalink.
- **Testes** com as fixtures de T2.2: quantidade de ofertas, campos obrigatórios preenchidos e um item conhecido conferido campo a campo. O HTML e o JSON da mesma página precisam gerar o mesmo conjunto de ids.

### T2.4 Job de coleta
- **Arquivo:** `collector/portal.py`. Função `collect(session, db, cfg) -> int`:
  1. Health check de login. Se falhar, levanta `SessionExpired`.
  2. Navega pelas páginas configuradas (`collector.pages`, `max_pages`) interceptando JSON.
  3. Faz o upsert e devolve o número de ofertas novas.
- **Testes:** com `page` falsa que reproduz as fixtures, o upsert e a contagem de novas ficam corretos; `SessionExpired` é levantado quando a fixture de login aparece.

---

## Fase 3: Link de afiliado

### T3.1 Geração de link
- **Arquivo:** `affiliate/linkgen.py`.
- `generate_link(session, offer) -> str`:
  1. Abre o permalink e espera a barra de afiliado.
  2. Clica em gerar/compartilhar e captura o link (por resposta de rede ou pela área de cópia, conforme o mapeado em T2.2).
  3. Fallback: abre o Gerador de link do portal, cola o permalink e lê o resultado.
- Rate limit: um token bucket com `affiliate.max_links_per_hour`.
- **Testes:** com `page` falsa das fixtures, o caminho principal funciona; o fallback é acionado quando o principal falha; o rate limit bloqueia acima do limite.

### T3.2 Validação do link
- **Arquivo:** `affiliate/validate.py`.
- `is_valid_format(link)`: regex para `mercadolivre.com(.br)?/(sec|social)/…`.
- `resolves_to(link, mlb_id)`: httpx sem navegador, segue os redirects (máx. 5) e procura o MLB id na URL final.
- **Testes** (respx): cadeia de redirects válida; MLB diferente → falso; timeout → falso, sem exceção.

### T3.3 Etapa de link no pipeline
- **Arquivo:** `pipeline.py`. Função `link_approved(session, db)`: `approved` → `linked` ou `link_failed` (com aviso ao admin via callback injetado).
- **Testes:** transições; falha dupla gera aviso; nunca muda para `linked` sem link válido.

---

## Fase 4: Criativo

### T4.1 Título curto
- **Arquivo:** `creative/title.py`. Função `short_title(title, max_len=60)`: remove códigos (`MLB…`, SKUs alfanuméricos longos), troca CAIXA ALTA por capitalização de título e corta sem partir palavra.
- **Testes:** casos reais das fixtures.

### T4.2 Templates de texto
- **Arquivos:** `creative/text.py`, `templates/text/{casa,tech}.txt` (5 modelos cada, separados por `---`).
- `render_caption(offer, niche, chat, db) -> NeutralText`: sorteia um modelo sem repetir o último do chat e preenche as variáveis. `{selos}` some se for vazio, junto com a linha.
- **Testes:** todas as variáveis são substituídas; o modelo não repete em sequência; a linha vazia de selos é removida.

### T4.3 Formatação por canal
- **Arquivo:** `creative/format.py`.
- `to_whatsapp(neutral)`: `*negrito*`, `~riscado~`.
- `to_telegram_html(neutral)`: `<b>` e `<s>`, com escape de `<&>`.
- **Testes:** escape de caracteres especiais no título; o link fica intacto; legenda do Telegram limitada a 1024 caracteres.

### T4.4 Imagem
- **Arquivos:** `creative/image/base.py`, `creative/image/themes.py`, `assets/fonts/` (Inter ou Poppins, licença OFL) e `assets/logos/` (placeholder por nicho).
- `render_card(offer, theme) -> bytes` (PNG 1080×1080) com:
  - fundo e moldura do tema;
  - foto do produto (download via httpx, troca o sufixo para a maior resolução, `contain` com fundo branco arredondado);
  - selo de % OFF, preço "de" riscado e preço "por" em destaque;
  - selos de Frete grátis/Full;
  - rodapé com QR code e link curto.
- CLI: `python -m ofertinhas render-sample <nicho>` gera `data/samples/<nicho>.png` para você revisar o visual.
- **Testes:** dimensões; o QR decodifica para o link exato (`pyzbar`); funciona sem preço original (sem selo de OFF); título longo não estoura a área.

### T4.5 Etapa de render no pipeline
- **Arquivo:** `pipeline.py`. Função `render_linked(db)`: `linked` → `rendered`; a imagem é salva em `data/cards/<mlb_id>-<niche>.png` e a legenda neutra no banco.
- **Testes:** transição e arquivos criados.

---

## Fase 5: Bot de aprovação

### T5.1 👤 Bot e ids
- Você cria o bot no BotFather e preenche `TELEGRAM_BOT_TOKEN` e `ADMIN_CHAT_ID` no `.env`.
- O comando `/chatid` (T5.4) ajuda a descobrir os ids dos grupos.

### T5.2 Card de aprovação
- **Arquivo:** `approval/messages.py`. Função `approval_card(offer, score)`: foto, título, preço, comissão (% e R$), selos, nota com breakdown por critério, nicho e prévia da legenda.
- Teclado inline: `✅ Aprovar`, `❌ Rejeitar`, `✏️ Editar texto` e `🔁 Trocar nicho`, com `callback_data` compacto (`a:<mlb>:<niche>`).
- **Testes:** formato do breakdown; `callback_data` ≤ 64 bytes.

### T5.3 Handlers
- **Arquivo:** `approval/bot.py`.
  - Aprovar → `approved`, e o card é editado para "✅ aprovado".
  - Rejeitar → `rejected`.
  - Editar → o bot pede o novo texto e salva a legenda customizada (que vale por cima do template).
  - Trocar nicho → lista os nichos possíveis.
- Guarda: só o `ADMIN_CHAT_ID` pode acionar; qualquer outro chat é ignorado e registrado em log.
- Envio dos `pending` com no máximo 1 card por oferta (marca `notified_at`).
- **Testes:** handlers com `Update` falso; usuário não admin é ignorado; aprovação idempotente (clique duplo).

### T5.4 Comandos
- **Arquivo:** `approval/commands.py`: `/corte`, `/peso`, `/pausar`, `/retomar`, `/fila`, `/top`, `/stats` e `/chatid` (este último funciona em qualquer chat, para descobrir ids).
- Os comandos de escrita gravam em `settings` e passam pela validação do `AppConfig`; um valor inválido gera uma resposta de erro sem salvar nada.
- **Testes:** cada comando altera o setting certo; argumento inválido gera mensagem de uso; `/top` pula a nota de corte, mas não o ritmo mínimo.

---

## Fase 6: Disparo

### T6.1 Ritmo
- **Arquivo:** `publisher/pacing.py`. Função pura `can_post(now, last_post_at, posts_today, pacing) -> (bool, next_allowed_at)`. O jitter é sorteado uma vez por post e guardado.
- **Testes** (freezegun): fora da janela; intervalo mínimo; limite diário; virada de dia no fuso de São Paulo.

### T6.2 Fila e revalidação
- **Arquivo:** `publisher/queue.py`.
- `next_for_chat(db, niche)` pega a `rendered`/`queued` de maior nota.
- `revalidate(offer)` consulta a página pública do produto via httpx (sem navegador) e compara o preço. Se o preço subir mais de 2% ou o produto estiver sem estoque, a oferta vai para `expired`.
- **Testes:** ordenação por nota; a expiração funciona; uma falha de rede na revalidação não expira a oferta (segue em frente e registra no log).

### T6.3 Telegram
- **Arquivo:** `publisher/telegram.py`. Função `send(chat_id, png, caption_html) -> message_id` via `sendPhoto`.
- **Testes** (respx): payload multipart correto; erro 429 respeita `retry_after`; erro 400 não faz retry.

### T6.4 👤 WhatsMiau
- Subir o WhatsMiau (pode ser local num VPS de teste) e parear o número dedicado por QR.
- Confirmar no README do `verbeux-ai/whatsmiau` a rota de mídia (provável `POST /message/sendMedia/{instance}`, no padrão da Evolution) e o formato do JID de grupo.
- Registrar o mapeamento em `docs/notes/whatsmiau-api.md`.

### T6.5 WhatsApp
- **Arquivo:** `publisher/whatsapp.py`.
  - `send(group_jid, png, caption)`: mídia em base64, legenda e `apikey` no header.
  - `send_presence(group_jid)` (digitando…), se a API suportar.
- **Testes** (respx): payload igual ao documentado em T6.4; timeout gera retry com backoff.

### T6.6 Etapa de disparo
- **Arquivo:** `pipeline.py`. Função `publish_due(db, cfg, senders, dry_run)`:
  1. Para cada nicho ativo, consulta `can_post` → `next_for_chat` → `revalidate`.
  2. Envia para o Telegram e depois para o WhatsApp, com intervalo aleatório entre os grupos do WhatsApp.
  3. Grava `record_post` por canal; até 3 tentativas com backoff e aviso ao admin se persistir.
  4. Em dry-run, todos os destinos viram o `ADMIN_CHAT_ID`.
- **Testes:** falha só no WhatsApp não reenvia ao Telegram; dry-run nunca toca chats reais; estado final `posted` quando ao menos um canal foi bem-sucedido.

---

## Fase 7: Orquestração

### T7.1 Scheduler
- **Arquivo:** `scheduler.py` com `AsyncIOScheduler` e jobs separados, cada um com try/except, log e aviso ao admin limitado a 1 por erro a cada 30 min:
  - `collect` (15 min) → `score_and_route` → notificar pendentes
  - `link_approved` (2 min)
  - `render_linked` (2 min)
  - `publish_due` (1 min)
  - `backup` (diário, 4h)
- `SessionExpired` pausa os jobs `collect` e `link_approved` até um `login-check` passar.
- **Testes:** exceção em um job não afeta os demais; `SessionExpired` pausa só os jobs de navegador; o aviso respeita o throttle.

### T7.2 CLI e main
- **Arquivo:** `__main__.py`:
  - `run [--dry-run]`: bot e scheduler no mesmo loop.
  - `collect-once`: imprime o ranking no terminal (útil para calibrar pesos).
  - `login-check`
  - `capture`
  - `render-sample`
- Logs estruturados com `logging` e formatter key=value.
- **Testes:** parse de argumentos; `collect-once` com sessão falsa imprime a tabela.

### T7.3 Backup
- **Arquivo:** `backup.py`: `sqlite3.backup()` para `data/backups/ofertinhas-YYYYMMDD.db`, mantendo 7 arquivos.
- **Testes:** rotação.

---

## Fase 8: Deploy

### T8.1 Docker
- **Arquivos:** `docker/Dockerfile` (base `mcr.microsoft.com/playwright/python:<versão fixa ≥ 2 semanas>`, usuário não root e `pip install .`), `docker/login-entrypoint.sh` (Xvfb, fluxbox, x11vnc com senha, websockify/noVNC na porta 6080 e Chromium visível com o perfil), `docker-compose.yml` e `Makefile` (`up`, `logs`, `login`, `dry-run`, `backup`).
- Serviços:
  - `ofertinhas`: worker, `restart: unless-stopped`.
  - `login`: profile `login`, mesma imagem, porta 6080 exposta.
  - `whatsmiau`: imagem oficial com tag fixa, porta 8080 só na rede interna, volume próprio.
- Volumes: `./data:/data` e `whatsmiau-data`.
- **Verificação:** `docker compose config` válido (roda no VPS ou no CI).

### T8.2 README
- Passo a passo: requisitos do VPS (Ubuntu 24.04, 2 vCPU e 4 GB), instalação do Docker, firewall (só 22, e 6080 durante o login), `.env`, BotFather, `/chatid`, pareamento do WhatsMiau, `make login`, `make dry-run` e `make up`.
- Seção de solução de problemas: sessão expirada, layout do ML mudou (como recapturar fixtures) e ban no WhatsApp.

### T8.3 👤 VPS
- Contratar o VPS, clonar o repositório, preencher `.env` e `config.yaml` (nichos e ids reais), `make login`, parear o WhatsApp.

---

## Fase 9: Validação ponta a ponta

### T9.1 👤 Dry-run
- `make dry-run` por 24 h. Todos os posts chegam só no seu chat.
- Checklist:
  - [ ] Coleta traz comissão, frete e Full corretos.
  - [ ] Notas fazem sentido (ajustar pesos com `collect-once`).
  - [ ] Links abrem o produto certo e aparecem no painel de afiliados.
  - [ ] Imagem e texto aprovados visualmente.
  - [ ] Ritmo respeitado.

### T9.2 👤 Go-live gradual
- Ligar **um** nicho (Telegram e WhatsApp) com `max_posts_per_day: 10` por 3 dias; depois os demais nichos.
- Subir para 25 posts/dia só se o WhatsApp não mostrar sinais de restrição.

---

## Dependências entre tarefas

```
T0 → T1.1–T1.7 ─────────────────────────────┐
T0 → T2.1 → T2.2👤 → T2.3 → T2.4 ────────────┤
              └────→ T3.1 → T3.2 → T3.3 ─────┤
T1.1 → T4.1 → T4.2 → T4.3 ; T4.4 → T4.5 ─────┤
T1.3 → T5.1👤 → T5.2 → T5.3 → T5.4 ──────────┤
T1.3 → T6.1 → T6.2 → T6.3 ; T6.4👤 → T6.5 → T6.6
                                             └→ T7 → T8 → T9
```

As fases 1, 4 e 6.1–6.3 não dependem do ML logado e podem avançar enquanto T2.2 (captura com sua conta) não acontece.
