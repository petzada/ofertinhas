# Ofertinhas — Design

**Data:** 2026-10-21
**Status:** aprovado em brainstorming, aguardando revisão final

## 1. Objetivo

Automação que roda sozinha 24/7 e:

1. Coleta ofertas novas do Mercado Livre com a % de comissão de afiliado.
2. Pontua cada oferta com um ranking configurável por nicho.
3. Aprova automaticamente as ofertas acima de uma nota de corte e manda as intermediárias para aprovação manual via Telegram.
4. Gera o link de afiliado da conta logada no Mercado Livre, só para ofertas aprovadas.
5. Monta texto (template fixo) e imagem promocional (template Pillow, sem IA) com preço, selos, link e QR code.
6. Dispara nos grupos de nicho do Telegram (bot do BotFather) e do WhatsApp (WhatsMiau), respeitando um ritmo controlado.

Contexto de negócio: anúncios no Meta Ads e no Google Ads levam pessoas para grupos de achadinhos por nicho. A automação mantém os grupos abastecidos com as melhores ofertas assim que elas aparecem.

## 2. Decisões tomadas

| Tema | Decisão |
|---|---|
| Fonte da comissão | Lista de ofertas do portal de afiliados (`afiliados.mercadolivre.com.br`), que mostra a % de comissão |
| Geração de link | Barra de afiliado na página do produto; plano B: Ferramentas → Gerador de link no portal |
| Hospedagem | VPS Linux, Docker Compose |
| Aprovação manual | Bot privado do Telegram com botões inline |
| Grupos | Um grupo por nicho (Telegram e WhatsApp), cada nicho com seu perfil de ranking |
| Imagem | Só template (Pillow), sem IA |
| Texto | Template fixo com variáveis, sem IA |
| Ritmo | Moderado: coleta a cada 15 min, ~1 post a cada 25 min por grupo, das 8h às 23h, até 25 posts/dia |
| Arquitetura | App Python único (abordagem A); n8n descartado |

## 3. Arquitetura

```
VPS (Docker Compose)
├── ofertinhas (Python 3.12)
│   ├── collector/   Playwright → portal de afiliados → ofertas cruas
│   ├── ranking/     nota 0–100 por perfil de nicho → aprovada / fila manual / descartada
│   ├── affiliate/   Playwright → barra de afiliado do produto → link /sec/
│   ├── creative/    template de texto + imagem Pillow (foto, de/por, % OFF, selos, link, QR)
│   ├── publisher/   Telegram (Bot API) + WhatsApp (WhatsMiau), com controle de ritmo
│   ├── approval/    bot privado: ✅ / ❌ / ✏️ e comandos de admin
│   └── db/          SQLite (offers, scores, links, posts, settings)
├── whatsmiau       (container oficial, porta 8080, volume da sessão)
└── novnc           (acesso ao Chromium para login no ML; profile "login", só sobe quando preciso)
```

**Stack:** Python 3.12, Playwright (Chromium), APScheduler, SQLite (via SQLAlchemy ou `sqlite3` + migrações simples), python-telegram-bot, Pillow, `qrcode`, httpx, PyYAML/pydantic para validar a config, pytest + respx.

**Princípio:** cada módulo é uma função isolada que lê o estado do banco, executa uma etapa e grava o novo estado. O processo pode cair e retomar de onde parou, e cada módulo é testável sozinho.

## 4. Ciclo de vida da oferta

```
collected → scored ─┬─ nota ≥ auto_approve_at    → approved
                    ├─ manual_review_at ≤ nota < auto_approve_at → pending → (✅) approved | (❌) rejected
                    └─ nota < manual_review_at   → discarded
approved → linked → rendered → queued → posted
              └→ link_failed (avisa o admin; nunca posta sem link)
queued → expired (preço mudou/sem estoque na revalidação)
```

- **collected:** id MLB, título, preço de/por, % comissão, categoria, URL da foto, avaliação, nº vendidos, frete grátis (bool), Full (bool), data da coleta. Se o id já existe, atualiza preço, comissão e selos.
- **scored:** nota calculada para cada nicho que casa com a oferta; fica o nicho de maior nota (ou todos, com `multi_niche: true`).
- **linked:** o link é gerado só após a aprovação, para economizar requisições ao ML.
- **posted:** registro separado por canal (Telegram e WhatsApp); a falha em um não afeta o outro.

## 5. Ranking e configuração

A configuração fica num `config.yaml` versionado. Ajustes feitos pelo bot ficam na tabela `settings` e valem por cima do arquivo.

```yaml
defaults:
  weights:               # soma livre; normalizado para 0–100
    commission_pct: 35   # % de comissão do afiliado
    discount_pct:   25   # % OFF (de/por)
    commission_brl: 15   # R$ estimado = preço × comissão
    rating:         10   # estrelas
    sold_count:     10   # prova social (escala log)
    freshness:       5   # oferta mais nova pontua mais
    free_shipping:   8   # booleano
    full:            7   # booleano (Mercado Envios Full)
  caps:                  # tetos para outliers não achatarem o lote
    commission_pct: 20
    discount_pct: 70
  filters:
    min_price: 15
    max_price: 3000
    min_rating: 4.0
    require_free_shipping: false
    require_full: false
    blocked_keywords: [usado, recondicionado, réplica]
  auto_approve_at: 80
  manual_review_at: 60
  repost_cooldown_days: 7    # o mesmo produto só volta se o preço cair ≥ repost_price_drop_pct
  repost_price_drop_pct: 10
  multi_niche: false
  pacing:
    min_interval_min: 25
    jitter_min: 5
    window: ["08:00", "23:00"]
    max_posts_per_day: 25
    whatsapp_between_groups_s: [30, 90]

niches:
  casa:
    categories: [MLB1574, MLB1499]
    keywords: [cozinha, organizador, airfryer]
    weights: { discount_pct: 35 }   # sobrescreve só o que mudar
    auto_approve_at: 75
    telegram_chat_id: -100123...
    whatsapp_group_jid: "1203...@g.us"
    template: casa
  tech:
    categories: [MLB1648, MLB1051]
    # ...
```

**Cálculo da nota:**
1. Os filtros eliminam a oferta antes do cálculo.
2. Os critérios numéricos são normalizados de 0 a 1 contra o lote coletado: `min(valor, cap) / max(lote, limitado ao cap)`. `sold_count` usa escala log. `freshness` decai linearmente em 24 h.
3. Os critérios booleanos (`free_shipping`, `full`) valem 0 ou 1.
4. Nota = Σ(peso × valor normalizado) / Σ pesos × 100.
5. Nicho: primeiro casa a categoria, depois as keywords. Uma oferta sem nicho é descartada.

A mensagem de aprovação mostra a nota detalhada por critério (ex.: "comissão 14% → 32/35").

**Comandos do bot (só do chat do admin):**

| Comando | Efeito |
|---|---|
| `/corte <nicho> <auto> <manual>` | Altera as notas de corte |
| `/peso <nicho> <critério> <valor>` | Altera um peso |
| `/pausar [nicho]` / `/retomar [nicho]` | Pausa ou retoma os disparos |
| `/fila [nicho]` | Lista ofertas pendentes e enfileiradas |
| `/top <nicho>` | Posta agora a melhor oferta pendente do nicho |
| `/stats` | Posts por nicho e dia |
| `/chatid` | Responde o id do chat (para configurar os grupos) |

## 6. Sessão logada, coleta e link de afiliado

**Sessão:**
- O Chromium roda com `launch_persistent_context` num volume `/data/chrome-profile`.
- No primeiro uso, ou quando a sessão expirar, o login é manual: `docker compose --profile login up novnc` e depois acesso ao noVNC (com senha) para entrar no ML e no portal de afiliados, inclusive 2FA e captcha.
- A automação nunca digita senha.

**Health check:** antes de cada ciclo, abre o portal. Se cair na tela de login, pausa a coleta e a geração de links e avisa o admin. As ofertas aprovadas aguardam na fila.

**Coleta:**
- Navega pela lista de ofertas do portal de afiliados.
- Fonte preferencial: respostas JSON interceptadas com `page.on("response")`.
- Fallback: seletores CSS isolados em `collector/selectors.py`.

**Geração do link:**
1. Abre a página do produto e aciona a barra de afiliado.
2. Captura o link `/sec/...` (ou `/social/...`).
3. Valida o formato e segue o redirect via HTTP, confirmando que chega ao MLB correto.
4. Se falhar, usa o Gerador de link do portal.
5. Se os dois falharem, marca `link_failed` e avisa o admin.

**Comportamento humano:**
- Pausas aleatórias de 2 a 6 s entre ações.
- Uma aba por vez.
- Limite configurável de links por hora (padrão: 30).

## 7. Criativo

**Texto:**
- De 5 a 10 modelos por nicho em `templates/text/<nicho>.txt`, separados por `---`. O sorteio nunca repete o último modelo usado no grupo.
- Variáveis disponíveis: `{titulo_curto}`, `{preco_de}`, `{preco_por}`, `{desconto}`, `{selos}`, `{nota}`, `{vendidos}`, `{link}`.
- `{titulo_curto}` remove códigos e o excesso de maiúsculas e corta em 60 caracteres sem partir palavra.
- `{selos}` vira "🚚 Frete grátis • ⚡ Full", conforme a oferta.
- A formatação neutra é convertida por canal: `*negrito*`/`~riscado~` no WhatsApp e HTML no Telegram.

**Imagem (Pillow, 1080×1080 PNG):**
- Fundo e moldura com a cor e o logo do nicho.
- Foto do produto em alta resolução.
- Selo "% OFF", preço de/por e selos de Frete grátis/Full.
- Rodapé com QR code e link curto.
- Os layouts ficam em `templates/image/<nicho>.py`, todos de uma base comum; fontes embutidas no repositório.

## 8. Disparo

- **Fila:** uma por grupo, ordenada pela nota. Ofertas autoaprovadas e aprovadas manualmente entram na mesma fila. O ritmo segue `pacing`, com override por nicho.
- **Revalidação:** antes de postar, consulta o preço atual. Se o preço subir ou o produto ficar sem estoque, a oferta vai para `expired`.
- **Telegram:** `sendPhoto` com legenda HTML no grupo ou canal; o bot precisa ser admin.
- **WhatsApp:** endpoint de mídia do WhatsMiau (compatível com a Evolution API), com imagem e legenda. Intervalo aleatório de 30 a 90 s entre grupos e presença "digitando…" quando suportado. Recomenda-se um número dedicado (risco de banimento de API não oficial).
- **Registro:** `posts(offer_id, channel, chat, message_id, sent_at, status)`. Falha → até 3 tentativas com backoff; se persistir, avisa o admin, e o outro canal segue normalmente.
- **Modo `--dry-run`:** ciclo completo real, mas todos os envios vão para o chat privado do admin.

## 9. Erros e observabilidade

- Falhas de rede: retry com backoff exponencial (3 tentativas).
- Exceção inesperada no Playwright: salva screenshot e HTML em `/data/debug/<timestamp>/` e manda um aviso curto ao admin.
- Um módulo que falha não derruba os outros: cada job do scheduler tem um try/except próprio.
- Logs estruturados em stdout (`docker compose logs`).
- Backup diário do SQLite em `/data/backups/`, mantendo 7 dias.

## 10. Testes

- **Unitários:** normalização e nota, roteamento de nicho, filtros, cooldown de repost, limpeza de título, render dos templates de texto, ritmo da fila (relógio falso) e transições de estado.
- **Parsers com fixtures:** HTML e JSON reais do portal e da página do produto em `tests/fixtures/`, sem abrir navegador.
- **Imagem:** confere as dimensões e que o QR code decodifica para o link correto (`pyzbar`).
- **Publisher:** Telegram e WhatsMiau mockados com `respx`, verificando o payload.
- **Validação real:** `--dry-run` antes de ligar os grupos.
- **Execução:** localmente, só os testes dos arquivos alterados; a suíte completa roda no GitHub Actions.

## 11. Deploy

- `docker-compose.yml` com os serviços `ofertinhas` (base `mcr.microsoft.com/playwright/python`), `whatsmiau` e `novnc` (profile `login`).
- `.env` para os segredos: `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `WHATSMIAU_URL`, `WHATSMIAU_API_KEY`, `WHATSMIAU_INSTANCE`, `NOVNC_PASSWORD`.
- Volumes: `/data` (SQLite, perfil do Chrome, debug, backups) e a sessão do WhatsMiau.
- O README cobre, passo a passo:
  1. Criar o bot no BotFather e colocá-lo como admin dos grupos.
  2. Obter os chat ids com `/chatid`.
  3. Parear o WhatsApp no WhatsMiau por QR.
  4. Fazer o primeiro login no ML pelo noVNC.
  5. Rodar o `--dry-run`.

## 12. Ordem de implementação

1. Núcleo: db, config (com validação), ranking
2. Coletor
3. Link de afiliado
4. Criativo (texto e imagem)
5. Bot de aprovação e comandos
6. Publisher e fila com ritmo
7. Docker, deploy e README

## 13. Fora do escopo (por enquanto)

Painel web, IA de imagem e de texto, múltiplas contas de afiliado, outras lojas (Shopee, Amazon) e métricas de clique próprias. A arquitetura não impede adicionar nenhum deles depois.

## 14. Riscos e pontos a verificar na implementação

- **Layout do portal de afiliados e da barra de afiliado:** a primeira tarefa do coletor e do módulo de link é capturar fixtures reais com a conta logada e mapear o JSON e os seletores.
- **Rotas exatas do WhatsMiau** para mídia em grupo: confirmar no README do `verbeux-ai/whatsmiau` ou na referência da Evolution API.
- **Termos de uso do ML e do programa de afiliados** sobre automação: manter volume baixo e comportamento humano.
- **Banimento no WhatsApp:** número dedicado, ritmo moderado e aquecimento gradual dos grupos.
