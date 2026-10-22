# Ofertinhas — Plano de implementação

**Spec:** [2026-10-21-ofertinhas-design.md](../specs/2026-10-21-ofertinhas-design.md) (revisão 2)
**Data:** 2026-10-21 · **Revisão 2:** 2026-10-22 (extensão no Brave + tudo local, sem VPS)

## Como executar este plano

- **Testes antes do código:** cada tarefa começa pelo teste que falha. Depois vem a implementação mínima até passar e, por fim, um commit.
- **Testes locais:** só os arquivos da tarefa (`pytest tests/<arquivo>` / `node --test extension/tests/<arquivo>`). A suíte completa roda no GitHub Actions. Nunca rodar lint e testes ao mesmo tempo.
- **Ambiente:** Windows, Python 3.13 no venv `.venv`, Node 22 (só para testar a extensão, sem dependências npm) e Brave.
- **Tarefas marcadas 👤 precisam de você.**

## Estrutura alvo

```
ofertinhas/
├── src/ofertinhas/
│   ├── __main__.py         # CLI: run [--dry-run], whatsapp-groups, render-sample, install-task
│   ├── settings.py         # .env
│   ├── config.py ✅  models.py ✅  db.py ✅  pipeline.py ✅  ranking/ ✅
│   ├── collector/
│   │   ├── parsers.py      # JSON bruto do portal → Offer
│   │   └── categories.py   # ancestrais via API pública de categorias, com cache
│   ├── api/
│   │   └── app.py          # FastAPI: /ext/config, /ext/raw, /ext/link-requests, /ext/links, /ext/alert, /health
│   ├── affiliate/
│   │   └── validate.py     # formato + redirect → MLB
│   ├── creative/           # title.py, text.py, format.py, image/
│   ├── approval/           # messages.py, bot.py, commands.py
│   ├── publisher/          # pacing.py, queue.py, telegram.py, whatsapp.py
│   ├── scheduler.py
│   ├── winops.py           # SetThreadExecutionState, tarefa de logon
│   └── backup.py
├── extension/
│   ├── manifest.json
│   ├── background.js       # alarmes, fila de links, freio
│   ├── content-main.js     # world MAIN: envolve fetch/XHR
│   ├── content-bridge.js   # world ISOLATED: repassa ao service worker
│   ├── lib/*.js            # funções puras (padrões, janela, detecção, rate limit)
│   ├── popup.html/js, options.html/js
│   └── tests/*.test.js     # node --test
├── templates/text/, assets/fonts/, assets/logos/
├── tests/ (+ tests/fixtures/portal/)
└── .github/workflows/ci.yml
```

---

## ✅ Fase 0: Base do projeto (concluída)
Scaffold, CLI, CI (ruff → pytest) e `.gitattributes`.

## ✅ Fase 1: Núcleo (concluída)
- `models.py`: `Offer` (produto) separado de `Candidate` (decisão por nicho).
- `config.py`: camadas defaults → nicho → overrides, com validação.
- `db.py`: ofertas, histórico de preço, candidatos, posts e settings.
- `ranking/`: filtros, nichos por ancestral de categoria e nota com alvos absolutos.
- `pipeline.score_and_route`: faixas de nota, cooldown, pausa e `multi_niche`.

---

## Fase 2: Saída do Playwright e mapeamento do portal

### T2.1 Remover o Playwright ✅
- Apagar `browser.py`, `capture.py` e seus testes. Tirar `playwright` do `pyproject.toml` e o comando `capture` da CLI.
- `slugify` vai para `ofertinhas/text.py` (com teste), porque o criativo e o debug ainda usam.
- Apagar `data/chrome-profile` e `data/capture/` (as capturas falhas).

### T2.2 👤 HAR do portal no Brave
Quando o limite de tentativas de login do ML liberar, no Brave normal:
1. Faça login no ML à mão.
2. Abra o DevTools (F12), aba **Network**, e marque **Preserve log**.
3. Abra a lista de ofertas do portal de afiliados com a % de comissão. Role, vá para a página 2 e aplique um filtro de categoria.
4. Gere um link pelo **Gerador de link** e outro pela **barra de afiliado** de um produto.
5. Clique com o botão direito na lista → **Save all as HAR** e salve em `data/har/portal.har`.

### T2.3 Ferramenta de extração do HAR ✅
- **Feito como comando da CLI:** `python -m ofertinhas har-extract data/har/portal.har --mask "Seu Nome=Pessoa Exemplo"` (código em `har.py`).
- Lê o HAR, **descarta todos os headers e cookies**, mantém método, URL, status, corpo da requisição e corpo da resposta JSON. Mascara e-mail, nome e ids de usuário com um mapa de substituição.
- Grava em `tests/fixtures/portal/NNN-<slug>.json` e gera um índice `tests/fixtures/portal/index.md`.
- **Testes:** HAR sintético com cookie, header `Authorization` e e-mail; a saída não contém nenhum dos três.

### T2.4 Mapeamento ✅
- **Feito:** `docs/notes/portal-mapping.md`, com fixtures em `tests/fixtures/portal/`. Lista em `hub/search` e link em `createLink` (`meli.la`); a extensão chama as duas de dentro da aba do portal. Frete grátis e Full não vêm na lista (ver T2.7).
- **Arquivo:** `docs/notes/portal-mapping.md`.
- Descreve quais URLs trazem a lista de ofertas e em que campo está cada dado: comissão, preço de/por, categoria, foto, avaliação, vendidos, frete grátis, Full e cupom.
- Registra qual chamada o Gerador de link faz (endpoint, método e corpo) e como a resposta traz o link.
- Define os padrões de URL de captura da extensão e a estratégia de link (endpoint ou formulário).

### T2.5 Parser da busca
- **Arquivo:** `collector/parsers.py`. `parse_hub_search(request_body, response_body) -> list[Offer] | None`, onde `None` significa formato desconhecido (o JSON é salvo em `data/unparsed/` e o admin é avisado).
- Campos conforme o mapeamento: MLB (`metadata.id`), `type`, `extra_commission`, URL, título, comissão (os 2 formatos do chip), preço atual e anterior, `pix_only` ("no Pix" no rótulo), avaliação, vendidos (`+5mil` → 5000), foto (`D_NQ_NP_2X_<id>-F.webp`), `international` (`cbt`) e destaque.
- A categoria vem do filtro `category` do pedido: `category_path = (id,)`, ou `()` sem filtro.
- Novos campos no `Offer` e no banco (migração 2): `item_type`, `extra_commission`, `pix_only`, `international`, `highlight`, `shipping_checked_at`.
- **Testes** com as 4 fixtures de busca: 18 ofertas por página; um item conferido campo a campo em cada formato de chip; Pix; internacional; sem avaliação; payload desconhecido devolve `None`.

### T2.6 Pix e internacional no criativo e nos filtros
- `{preco}` e o card mostram "no Pix" quando `pix_only`.
- Filtro `exclude_international` (padrão `false`).
- **Testes:** legenda e card com Pix; filtro.

### T2.7 Frete grátis e Full: adiada ⏸️
- As páginas de produto salvas vieram como desafio reCAPTCHA. O ML barra o acesso ao HTML do produto fora da navegação normal.
- **Decisão do usuário (2026-10-22):** frete grátis e Full saem do ranking por enquanto (pesos 0 em `config.py` e `config.example.yaml`). Os campos `free_shipping`, `full` e `shipping_checked_at` e `db.set_shipping` ficam prontos para uma fonte futura.

---

## Fase 3: API local do backend

### T3.1 Settings e token ✅
- **Arquivo:** `settings.py`, que carrega o `.env`, e `.env.example`.
- Variáveis: `EXTENSION_TOKEN`, `API_PORT=8765`, `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `WHATSMIAU_API_KEY` e `WHATSMIAU_INSTANCE`.
- CLI: `python -m ofertinhas new-token` gera o token e mostra onde colocá-lo.

### T3.2 App FastAPI ✅ (por enquanto só `/health`; as rotas `/ext/*` entram a partir de T3.3)
- **Arquivo:** `api/app.py`. `create_app(conn, cfg, notifier)`.
- Middleware de token. CORS só para a origem `chrome-extension://<id>`, configurável.
- **Testes** (TestClient): sem token → 401; token errado → 401; `/health` ok.

### T3.3 `/ext/config` e `/ext/raw`
- `/ext/config` devolve os padrões de URL, as URLs da lista, `collect_every_min`, a janela de horário e o estado de pausa (tabela `settings`).
- `/ext/raw`:
  1. Faz o parse.
  2. Para cada oferta: `category_path` e depois `upsert_offer`.
  3. Roda `score_and_route` nos ids novos ou atualizados.
  4. Responde `{parsed, new, approved, pending}`.
  - Um payload desconhecido é salvo e responde `{parsed: 0, unknown: true}`.
- **Testes:** com a fixture real, as ofertas e os candidatos são criados; o mesmo payload duas vezes não duplica; payload desconhecido.

### T3.4 Pedidos de link
- `GET /ext/link-requests`: a candidata `approved` de maior nota, cujo produto não tem link e não foi pedido nos últimos 10 min. Marca `link_requested_at`.
- `POST /ext/links`:
  1. Valida o link (T3.5).
  2. Se válido, chama `set_affiliate_link` e passa todas as candidatas `approved` do produto para `linked`.
  3. Se não, soma uma tentativa; na 3ª, marca `link_failed` e avisa o admin.
- Migração: `offers.link_requested_at` e `offers.link_attempts`.
- **Testes:** ordem por nota; não repete o pedido em 10 min; link reaproveitado entre nichos; três falhas viram `link_failed` com aviso.

### T3.5 Validação de link
- **Arquivo:** `affiliate/validate.py`.
- `is_valid_format`: regex para `https://meli.la/<id>` (formato real visto no mapeamento).
- `GET /ext/link-requests` devolve o corpo pronto do `createLink` (`itemId`, `type`, `extraCommission`, `itemAddToList`, `tag` de `ML_AFFILIATE_TAG`, `urls`, `buyBoxWinner`). `POST /ext/links` também guarda o código de busca (`regex`), que vira `{codigo_busca}` na legenda.
- `resolves_to(link, mlb_id)`: httpx segue até 5 redirects e procura o MLB na URL final.
- **Testes** (respx): cadeia válida; MLB diferente; timeout devolve falso, sem exceção.

### T3.6 `/ext/alert` e pausa
- Grava `extension_paused = {reason, url, at}`, avisa o admin (limitado a 1 por motivo a cada 30 min) e passa a responder `paused: true` em `/ext/config`.
- `/retomar coleta` (Fase 6) limpa a pausa.
- **Testes:** alerta pausa e notifica; um segundo alerta igual em 30 min não notifica de novo.

---

## Fase 4: Extensão no Brave

### T4.1 Funções puras (`extension/lib/`) ✅
- `matchesCapture(url, patterns)`
- `withinWindow(now, window)`
- `nextDelayMs(baseMin, jitterMin, rng)`
- `detectBlock({url, status, html?})`, que devolve `'login' | 'captcha' | 'http' | null`
- `RateLimiter(maxPerHour)`
- **Testes** (`node --test`): todos os casos, incluindo a URL de login que vimos (`/login/identification`, `no-feasible-authenticators`).

### T4.2 Manifesto e captura
- `manifest.json` (MV3):
  - `permissions`: `alarms`, `storage`, `tabs`, `scripting`.
  - `host_permissions`: domínios do ML e `http://127.0.0.1:8765/*`.
- `content-main.js` (world MAIN, `document_start`) envolve `fetch` e `XMLHttpRequest`. Clona as respostas que casam com os padrões e as envia com `postMessage`.
- `content-bridge.js` (world ISOLATED) repassa via `chrome.runtime.sendMessage`.
- O service worker envia ao backend `POST /ext/raw`.
- **Teste manual (checklist):** abrir a lista do portal, conferir no `/health`/logs que os payloads chegaram e que as ofertas aparecem no banco.

### T4.3 Ciclo de coleta
- O wrapper de `fetch`/XHR guarda o último `x-csrf-token` e o `x-custom-origin` das chamadas da própria página.
- O alarme `collect` busca `/ext/config`. Se estiver pausado ou fora da janela, só reagenda.
- Senão, garante a aba fixada do portal e, para cada categoria e página, chama `hub/search` de dentro da aba (`chrome.scripting.executeScript`, world MAIN), com 5 a 15 s entre chamadas. Envia `{url, request_body, status, body}` ao `POST /ext/raw`.
- 401/403: recarrega a aba uma vez para renovar o token; se falhar de novo, ou se `detectBlock` acusar algo, aciona o freio (para os alarmes, `POST /ext/alert` e salva o estado).

### T4.4 Geração de link
- O alarme `links` consulta `GET /ext/link-requests` e atende no máximo um pedido, respeitando o `RateLimiter` e 30 a 90 s desde o último.
- Faz o `POST createLink` de dentro da aba do portal com o corpo que veio do backend e manda `short_url`, `regex` e `total_error` para o `POST /ext/links`. Um 401/403/429 aciona o freio.


### T4.5 Popup e opções
- **Opções:** URL do backend e token, salvos em `chrome.storage.local`.
- **Popup:**
  - Estado (ativa, pausada ou fora da janela) e o motivo da pausa.
  - Última coleta e quantas ofertas vieram.
  - Links gerados hoje.
  - Botões Pausar/Retomar (o Retomar limpa a pausa no backend via `POST /ext/resume`).

### T4.6 👤 Instalação no Brave
- `brave://extensions` → Modo desenvolvedor → Carregar sem compactação → pasta `extension/`.
- Colar o token nas opções.
- Fixar a aba do portal.
- Ligar "continuar executando apps em segundo plano".

---

## ✅ Fase 5: Criativo
Sem mudanças em relação à revisão 1:
- **T5.1** título curto
- **T5.2** templates de texto (sorteio sem repetir; inclui `{cupom}` se T2.7 existir)
- **T5.3** formatação por canal
- **T5.4** imagem Pillow 1080×1080 com QR e `render-sample <nicho>`
- **T5.5** etapa `linked → rendered`

Testes conforme a spec, incluindo o QR decodificando para o link exato (`pyzbar`).

## Fase 6: Bot de aprovação (✅ T6.2–T6.4; falta T6.1 👤)
- **T6.1 👤** Criar o bot no BotFather e preencher o `.env`.
- **T6.2** Card de aprovação com foto, nota e breakdown, e teclado inline (`callback_data` ≤ 64 bytes).
- **T6.3** Handlers: aprovar, rejeitar, editar texto e trocar nicho. Só o admin pode usar, e o clique duplo é idempotente.
- **T6.4** Comandos: `/corte`, `/peso`, `/pausar [nicho|coleta]`, `/retomar [nicho|coleta]`, `/fila`, `/top`, `/stats`, `/chatid`. As escritas são validadas pelo `AppConfig`.

## Fase 7: Disparo

### T7.1 Ritmo ✅
Função pura `can_post(now, last_post_at, posts_today, pacing)` (testada com freezegun).

### T7.2 Fila e validade ✅ (com `Offer.last_seen_at` e `max_offer_age_hours` no config)
- `next_for_chat(db, niche)`: a candidata `rendered`/`queued` de maior nota.
- Validade: se o `updated_at` da oferta for mais antigo que `max_offer_age_hours`, a candidata vira `expired`.
- **Testes:** ordenação; expiração.

### T7.3 Telegram ✅
`sendPhoto` com legenda HTML via httpx. Testes com respx: payload; 429 respeita `retry_after`; 400 sem retry.

### T7.4 👤 Teste da API da WhatsMiau.dev
- Com a sua instância já conectada no painel: `python -m ofertinhas whatsapp-groups` lista os grupos e JIDs (`GET /group/fetchAllGroups`).
- Enviar **uma** imagem de teste para um **grupo de teste seu**, duas vezes: com `media` em URL pública e com `media` em base64. **Este envio precisa da sua confirmação na hora.**
- Registrar o resultado em `docs/notes/whatsmiau.md`.
- Se o base64 não funcionar, decidir com você a hospedagem da imagem (por exemplo, um bucket público do Cloudflare R2) e incluir uma tarefa para isso.

### T7.5 Cliente WhatsApp
- **Arquivo:** `publisher/whatsapp.py`.
  - `send_image(jid, image, caption)`: `POST /message/sendMedia/{instância}`.
  - `send_presence(jid)`: `POST /chat/sendPresence/{instância}`, se o teste de T7.4 mostrar suporte a grupo.
  - `list_groups()`.
- **Testes** (respx): header `apikey`, payload igual ao validado em T7.4; timeout gera retry com backoff.

### T7.6 Etapa de disparo
- `publish_due(db, cfg, senders, dry_run)`:
  1. Para cada nicho ativo: `can_post` → `next_for_chat` → validade.
  2. Envia para o Telegram e depois para o WhatsApp, com 30 a 90 s entre grupos do WhatsApp.
  3. Grava `record_post` por canal.
  4. Em dry-run, os destinos são o admin e o grupo de teste.
- **Testes:** falha só no WhatsApp não reenvia ao Telegram; dry-run nunca toca grupos reais; `posted` quando ao menos um canal teve sucesso.

---

## Fase 8: Orquestração e operação no Windows

### T8.1 Scheduler
- Jobs, cada um com try/except, log e aviso ao admin com throttle:
  - `render_linked` (1 min)
  - `publish_due` (1 min)
  - `notify_pending` (1 min)
  - `expire_stale` (15 min)
  - `backup` (diário, às 4h)
- **Testes:** exceção isolada por job; throttle do aviso.

### T8.2 `run`
- O bot (long polling), o uvicorn e o APScheduler rodam no mesmo loop asyncio.
- Logs rotativos em `data/logs/`.
- `--dry-run` muda os destinos.
- **Testes:** parse de argumentos; inicialização e encerramento com componentes falsos.

### T8.3 Windows
- **Arquivo:** `winops.py`.
  - `keep_awake(active: bool)` via `ctypes` `SetThreadExecutionState`; o scheduler liga na janela de postagem e desliga fora dela.
  - `install-task`: cria a tarefa "Ofertinhas" no Agendador (`schtasks /Create /SC ONLOGON`) rodando `pythonw -m ofertinhas run` no diretório do projeto.
- **Testes:** os flags passados (com a função do Windows mockada) e o comando `schtasks` montado.

### T8.4 Backup e README
- Backup diário do SQLite mantendo 7 arquivos (com teste de rotação).
- O README cobre, passo a passo:
  1. Requisitos e venv.
  2. `.env`.
  3. BotFather e `/chatid`.
  4. Instância e grupos na WhatsMiau.dev.
  5. Extensão no Brave.
  6. `install-task`.
  7. Dry-run.
  8. Solução de problemas: extensão pausada, ML mudou o formato (gravar um HAR novo), PC suspenso.

---

## Fase 9: Validação

### T9.1 👤 Dry-run de 1 a 2 dias
- [ ] A coleta traz comissão, preço, frete, Full (e cupom).
- [ ] As notas fazem sentido (ajustar com `/peso` e `/corte`).
- [ ] Os links abrem o produto certo e aparecem no painel de afiliados.
- [ ] Imagem e texto aprovados.
- [ ] O ritmo é respeitado.
- [ ] O freio da extensão funciona (testar deslogando de propósito).

### T9.2 👤 Entrada gradual
Um nicho com no máximo 10 posts/dia por 3 dias; depois os demais e o limite cheio.

---

## Dependências

```
Fase 1 ✅ ──┬─ T2.1 → T2.2👤 → T2.3 → T2.4 → T2.5 → T2.6 (→ T2.7)
            ├─ T3.1 → T3.2 → T3.3 (precisa de T2.5) → T3.4 → T3.5 → T3.6
            ├─ T4.1 → T4.2 → T4.3 → T4.4 (precisa de T2.4 e T3.4) → T4.5 → T4.6👤
            ├─ Fase 5 (independente)
            ├─ Fase 6 (T6.1👤)
            └─ T7.1–T7.3 ; T7.4👤 → T7.5 → T7.6
                                       └→ Fase 8 → Fase 9👤
```

**Pode andar sem o HAR:** T2.1, T2.3, T3.1, T3.2, T4.1, a Fase 5 inteira, a Fase 6 e T7.1–T7.3.
