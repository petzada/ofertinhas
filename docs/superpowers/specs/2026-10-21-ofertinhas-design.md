# Ofertinhas — Design

**Data:** 2026-10-21 · **Revisão 2:** 2026-10-22
**Status:** revisão 2 aguardando aprovação

> **Por que a revisão 2:** nas duas tentativas de captura, o login foi bloqueado no navegador automatizado (Playwright). O Google recusou o "Entrar com Google" e o Mercado Livre respondeu "limite de tentativas" logo após a verificação de navegador. Por isso a coleta e a geração de link saem do Playwright e passam para uma **extensão no Brave do usuário, já logado**. Também saem o VPS e o Docker: tudo roda no computador do usuário. O WhatsApp passa a ser só chamadas à **API da WhatsMiau.dev** (serviço pago do usuário, nada é hospedado por nós).

## 1. Objetivo

Automação que roda no computador do usuário e:

1. Coleta ofertas novas do portal de afiliados do Mercado Livre, com a % de comissão.
2. Pontua cada oferta com um ranking configurável por nicho.
3. Aprova automaticamente as ofertas acima de uma nota de corte e manda as intermediárias para aprovação manual via Telegram.
4. Gera o link de afiliado da conta logada, só para ofertas aprovadas.
5. Monta o texto (template fixo) e a imagem promocional (template Pillow, sem IA) com preço, selos, link e QR code.
6. Dispara nos grupos de nicho do Telegram (bot do BotFather) e do WhatsApp (API da WhatsMiau.dev), com ritmo controlado.

Contexto de negócio: anúncios no Meta Ads e no Google Ads levam pessoas para grupos de achadinhos por nicho. A automação mantém os grupos abastecidos com as melhores ofertas.

## 2. Decisões tomadas

| Tema | Decisão |
|---|---|
| Fonte da comissão | Lista de ofertas do portal de afiliados do ML, que mostra a % de comissão |
| Coleta e link de afiliado | Extensão própria (Manifest V3) no **Brave** do usuário, com a sessão real e logada à mão |
| Onde roda | Tudo no computador do usuário: Brave com a extensão + backend Python local. Sem VPS e sem Docker |
| WhatsApp | Endpoints da API da WhatsMiau.dev (`https://api.whatsmiau.dev/v2`) com a API key do usuário |
| Aprovação manual | Bot privado do Telegram com botões inline |
| Grupos | Um grupo por nicho (Telegram e WhatsApp), cada nicho com seu perfil de ranking |
| Imagem | Só template (Pillow), sem IA |
| Texto | Template fixo com variáveis, sem IA |
| Ritmo | Moderado: coleta a cada ~20 min, ~1 post a cada 25 min por grupo, das 8h às 23h, até 25 posts/dia |
| Arquitetura | Backend Python único (ranking, bot, criativo, disparo) + extensão como "braço" dentro do navegador |

## 3. Arquitetura

```
Computador do usuário
├── Brave (aberto e logado no ML)
│   └── extensão "Ofertinhas" (MV3, JavaScript sem build)
│       ├── coleta: recarrega a lista do portal em intervalos e repassa as respostas JSON
│       ├── links: pega pedidos de link do backend, gera no portal e devolve
│       └── freio: tela de login, captcha ou erro → para tudo e avisa o backend
│
└── backend "ofertinhas" (Python 3.12+, um processo, iniciado com o Windows)
    ├── api/        HTTP local (127.0.0.1) só para a extensão, com token
    ├── collector/  parsers: JSON bruto do portal → Offer (testados com fixtures do HAR)
    ├── ranking/    nota 0–100 por nicho → aprovada / fila manual / descartada   ✅ pronto
    ├── approval/   bot privado: ✅ / ❌ / ✏️ e comandos de admin
    ├── creative/   template de texto + imagem Pillow (foto, de/por, % OFF, selos, link, QR)
    ├── publisher/  Telegram Bot API + API da WhatsMiau.dev, com controle de ritmo
    └── db/         SQLite (offers, candidates, posts, settings)                  ✅ pronto
```

**Stack do backend:** Python, FastAPI + uvicorn (no mesmo loop asyncio do bot e do agendador), APScheduler, SQLite, python-telegram-bot (long polling, sem URL pública), Pillow, `qrcode`, httpx, pydantic, pytest + respx. **Sem Playwright.**

**Princípio:** a extensão é um repassador fino, com o mínimo de lógica: captura respostas, executa pedidos e reporta. Parsing, regras e decisões ficam no Python, onde são testáveis com fixtures reais. Quando o ML mudar algo, a correção acontece no backend, e na maioria dos casos a extensão não precisa ser atualizada.

## 4. Ciclo de vida da oferta

Cada oferta (`Offer`, o produto) tem uma decisão por nicho (`Candidate`):

```
coletada → nota por nicho ─┬─ nota ≥ auto_approve_at              → approved
                           ├─ manual_review_at ≤ nota < auto      → pending → (✅) approved | (❌) rejected
                           └─ nota < manual_review_at             → discarded
approved → linked → rendered → queued → posted
     └→ link_failed (avisa o admin; nunca posta sem link)
queued → expired (oferta não reapareceu na coleta dentro de max_offer_age_hours)
```

- **Repost:** uma oferta `posted` ou `rejected` só volta depois de `repost_cooldown_days`, ou antes disso se o preço cair `repost_price_drop_pct`.
- **Sem `multi_niche`:** a oferta vai só para o nicho de maior nota e fica bloqueada em todos os nichos enquanto estiver no fluxo ou em cooldown.
- **Validade:** o preço e a disponibilidade vêm da coleta mais recente. Antes de postar, a oferta precisa ter sido vista na coleta nas últimas `max_offer_age_hours` (padrão 6 h), sem nenhuma requisição extra ao ML.

## 5. Ranking e configuração

A configuração fica num `config.yaml` versionado. Ajustes feitos pelo bot ficam no banco e valem por cima do arquivo. **Esta parte já está implementada e testada (Fase 1).**

```yaml
multi_niche: false

defaults:
  weights:               # soma livre; normalizado para 0–100
    commission_pct: 35
    discount_pct:   25
    commission_brl: 15
    rating:         10
    sold_count:     10
    freshness:       5
    free_shipping:   8
    full:            7
  targets:               # valor que vale nota máxima no critério
    commission_pct: 20
    discount_pct: 60
    commission_brl: 40
    sold_count: 5000
    rating_floor: 4.0
    freshness_hours: 24
  filters: {min_price: 15, max_price: 3000, min_rating: 4.0,
            require_free_shipping: false, require_full: false,
            blocked_keywords: [usado, recondicionado, réplica]}
  auto_approve_at: 80
  manual_review_at: 60
  repost_cooldown_days: 7
  repost_price_drop_pct: 10
  pacing: {min_interval_min: 25, jitter_min: 5, window: ["08:00", "23:00"],
           max_posts_per_day: 25, whatsapp_between_groups_s: [30, 90]}

niches:
  casa:
    categories: [MLB1574]
    keywords: [airfryer]
    weights: {discount_pct: 35}
    telegram_chat_id: -100123...
    whatsapp_group_jid: "1203...@g.us"
```

**Cálculo da nota:**
1. Os filtros eliminam a oferta antes do cálculo.
2. Cada critério é normalizado de 0 a 1 contra um alvo absoluto (`targets`). `sold_count` usa escala log, `rating` vai de `rating_floor` até 5 e `freshness` decai linearmente.
3. Nota = Σ(peso × valor normalizado) / Σ pesos × 100, guardada com o breakdown por critério.
4. O nicho é escolhido primeiro pela categoria (qualquer ancestral), depois por keywords.

O caminho de ancestrais da categoria vem da API pública de categorias do ML (`/categories/{id}`), com cache no banco. Se a API não responder, a oferta casa só por keywords.

**Cupom:** o portal não expõe cupom na lista, então esse critério fica de fora por enquanto.

**Desconto só no Pix:** quando o rótulo de desconto da oferta diz "no Pix", a oferta é marcada (`pix_only`). O texto e o card mostram "no Pix" junto do preço, para não anunciar um preço que só vale com Pix como se fosse geral.

**Internacional:** ofertas de compra internacional vêm marcadas (`international`). O filtro opcional `exclude_international` (padrão `false`) as tira de um nicho.

**Comandos do bot (só no chat do admin):** `/corte`, `/peso`, `/pausar`, `/retomar`, `/fila`, `/top`, `/stats` e `/chatid`. `/pausar` e `/retomar` também valem para a extensão (`/pausar coleta`).

## 6. Extensão no Brave (coleta e link de afiliado)

**Instalação:** a pasta `extension/` do repositório é carregada como extensão descompactada (`brave://extensions`, modo desenvolvedor). Nas opções da extensão ficam a URL do backend (`http://127.0.0.1:8765`) e o token.

**Login:** feito à mão pelo usuário no Brave, uma única vez. A extensão nunca preenche login, senha nem código. No portal de afiliados, o Brave Shields pode ser desligado se atrapalhar.

**Coleta** (revisada após o mapeamento em `docs/notes/portal-mapping.md`):
- A lista vem de `POST /affiliate-program/api/hub/search`, paginada de 18 em 18 e com filtro por categoria. A oferta não traz a categoria, e a página 1 não aparece como chamada separada. Por isso a coleta é **ativa, de dentro da aba fixada do portal**: a extensão faz as mesmas chamadas que a página faz quando a pessoa rola a lista ou troca o filtro.
- A cada `collect_every_min` (padrão 20) ± variação aleatória, só dentro da janela de horário, a extensão chama `hub/search` para cada categoria dos nichos (`collect_pages_per_category`, padrão 3), com 5 a 15 s entre chamadas (~36 chamadas por hora com 4 categorias).
- As chamadas usam o `x-csrf-token` que a página já manda nas próprias requisições. O wrapper de `fetch`/XHR (world MAIN) guarda o último token visto. Se der 401/403, a aba é recarregada uma vez; se falhar de novo, o freio é acionado.
- Cada resposta vai para o backend em `POST /ext/raw`, junto com o corpo do pedido. A categoria do filtro vira o `category_path` da oferta, então o nicho é exato. Sem filtro, o nicho sai só por palavras-chave.
- O backend define as categorias, as páginas e os intervalos em `GET /ext/config`. Mudar isso não exige atualizar a extensão.

**Frete grátis e Full: fora do ranking por enquanto.**
- A lista do portal não traz esses dados, e a API pública de itens responde 403.
- A busca da página do produto foi testada e descartada: o ML responde a acessos ao HTML do produto fora da navegação normal com um desafio reCAPTCHA. Insistir acionaria o freio o tempo todo e marcaria a sessão como suspeita.
- Os pesos `free_shipping` e `full` ficam em 0 e os selos não aparecem. Os campos continuam no modelo; se surgir uma fonte confiável (por exemplo, a API oficial com um app de desenvolvedor), basta preenchê-los e religar os pesos.

**Link de afiliado:**
- Um alarme a cada ~2 min consulta `GET /ext/link-requests` (ofertas `approved` sem link).
- Atende **um pedido por vez**, com 30 a 90 s entre pedidos, até `max_links_per_hour` (padrão 30).
- A extensão chama, de dentro da aba do portal, o mesmo endpoint do Gerador de link: `POST /affiliate-program/api/v2/affiliates/createLink` com `{itemId, type, extraCommission, itemAddToList, tag, urls: [url], buyBoxWinner}`. O backend monta esse corpo com os dados guardados da oferta e a `tag` do afiliado (`ML_AFFILIATE_TAG`).
- A resposta traz o link curto **`https://meli.la/<id>`** e o código para colar no buscador do app (`regex`, por exemplo `QL81M2-HWKB`). O código fica disponível na legenda como `{codigo_busca}`.
- O resultado volta em `POST /ext/links`. O backend valida o formato (`https://meli.la/<id>`) e segue o redirect via HTTP até conferir que chega ao MLB certo. Depois de 3 falhas, marca `link_failed` e avisa o admin.

**Freio de segurança:** se a aba cair na tela de login, aparecer captcha ou chegar 401/403/429 do ML, a extensão:
1. para todos os alarmes;
2. avisa o backend em `POST /ext/alert`, que repassa ao admin no Telegram;
3. só volta com "Retomar" no popup ou com `/retomar coleta` no bot.

Não há retentativas automáticas contra o ML.

**Popup:** mostra o estado (ativa ou pausada e o motivo), a última coleta, os links gerados hoje e os botões Pausar/Retomar.

**Princípios contra banimento:** login manual, IP e aparelho de casa, leitura passiva do que a página já carrega, ritmo humano com variação, volume baixo (link só para aprovadas), uma aba por vez e parada imediata a qualquer sinal de bloqueio. Mesmo assim, há um risco residual: automação pode contrariar os termos do ML.

## 7. API local do backend

- Escuta só em `127.0.0.1:8765`.
- Todas as rotas exigem o header `X-Ofertinhas-Token`. O CORS aceita apenas a origem da extensão.

| Rota | Uso |
|---|---|
| `GET /ext/config` | Categorias, páginas por categoria, intervalos, janela e pausa |
| `POST /ext/raw` | `{url, request_body, status, body, captured_at}` → parse → upsert → ranking |
| `GET /ext/link-requests` | Próximo pedido de link com o corpo pronto do `createLink`, ou vazio |
| `POST /ext/links` | `{mlb_id, link}` ou `{mlb_id, error}` |
| `POST /ext/alert` | `{reason, url}` → pausa a coleta e avisa o admin |
| `GET /health` | Estado do backend |

## 8. Criativo

**Texto:**
- De 5 a 10 modelos por nicho em `templates/text/<nicho>.txt`, separados por `---`. O sorteio não repete o último modelo usado no grupo.
- Variáveis: `{titulo_curto}`, `{preco_de}`, `{preco_por}`, `{desconto}`, `{selos}`, `{cupom}`, `{nota}`, `{vendidos}`, `{link}`.
- A formatação é convertida por canal: `*negrito*`/`~riscado~` no WhatsApp e HTML no Telegram.

**Imagem (Pillow, 1080×1080 PNG):** fundo e moldura do nicho, foto do produto, selo "% OFF", preço de/por, selos de Frete grátis/Full e rodapé com QR code e link curto.

## 9. Disparo

- **Fila:** uma por grupo, ordenada pela nota, seguindo `pacing` (com override por nicho). Antes de postar, a oferta passa pela checagem de validade (seção 4).
- **Telegram:** `sendPhoto` com legenda HTML. O bot precisa ser admin do grupo. O bot usa long polling, então não precisa de URL pública.
- **WhatsApp (API da WhatsMiau.dev):**
  - Base `https://api.whatsmiau.dev/v2`, header `apikey: <chave>` e instância já conectada pelo usuário no painel da WhatsMiau.dev.
  - Imagem: `POST /message/sendMedia/{instância}` com `{"number": "<jid>@g.us", "mediatype": "image", "media": ..., "caption": ...}`.
  - Presença "digitando…": `POST /chat/sendPresence/{instância}`, se aceitar JID de grupo.
  - Descoberta dos JIDs: `GET /group/fetchAllGroups/{instância}`, exposta no comando `python -m ofertinhas whatsapp-groups`.
  - Intervalo aleatório de 30 a 90 s entre grupos.
  - **A verificar no primeiro teste** (a documentação não mostra): se `number` aceita JID `@g.us` e se `media` aceita base64. A documentação só cita URL pública. Se base64 não funcionar, a imagem precisa de um endereço público; a solução (por exemplo, um bucket público do Cloudflare R2) será escolhida nesse momento.
- **Registro:** `posts(offer_id, channel, chat, message_id, sent_at, status)`. Uma falha gera até 3 tentativas com backoff; se persistir, o admin é avisado e o outro canal segue normalmente.
- **Modo `--dry-run`:** o ciclo completo roda de verdade, mas os envios vão só para o chat privado do admin no Telegram e para um número/grupo de teste no WhatsApp.

## 10. Operação no Windows

- **Backend:**
  - Agendador de Tarefas do Windows, "ao fazer logon", rodando `pythonw -m ofertinhas run` no venv do projeto.
  - Logs rotativos em `data/logs/`.
  - Durante a janela de postagem, o backend pede ao Windows para não suspender (`SetThreadExecutionState`) e libera fora dela.
- **Brave:** precisa estar aberto com a extensão. Recomenda-se ligar "continuar executando apps em segundo plano" para os alarmes continuarem com a janela fechada.
- **Se o computador desligar:** nada se perde. A fila fica no SQLite e retoma ao ligar; ofertas velhas expiram pela regra de validade.
- **Backup:** cópia diária do SQLite em `data/backups/`, mantendo 7 dias.
- **Segredos:** `.env` com `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `WHATSMIAU_API_KEY`, `WHATSMIAU_INSTANCE` e `EXTENSION_TOKEN`.

## 11. Erros e observabilidade

- Chamadas de rede do backend (Telegram, WhatsMiau.dev, API de categorias): retry com backoff exponencial, 3 tentativas.
- Um JSON do portal que o parser não reconhece é salvo em `data/unparsed/` e gera um aviso ao admin (no máximo 1 por hora): sinal de que o ML mudou o formato.
- Cada job do agendador tem um try/except próprio: um job que falha não derruba os outros.
- `/stats` e o popup da extensão mostram a saúde do sistema.

## 12. Testes

- **Backend (pytest):** unitários (já cobrindo a Fase 1); parsers com fixtures reais extraídas do HAR; API local com o `TestClient` do FastAPI; criativo (o QR code precisa decodificar para o link exato); publisher com Telegram e WhatsMiau.dev mockados (`respx`).
- **Extensão (`node --test`, sem dependências):** funções puras em módulos separados, como o casamento de padrões de URL, a janela de horário, a detecção de login/captcha e o rate limit. A integração com o Brave é validada à mão, com um checklist.
- **Execução:** localmente, só os testes dos arquivos alterados; a suíte completa roda no GitHub Actions.

## 13. Ordem de implementação

1. ✅ Núcleo: db, config, ranking, pipeline de decisão
2. Remover o Playwright; mapear o portal pelo HAR gravado à mão no Brave; parsers com fixtures
3. API local do backend
4. Extensão: coleta, links, freio e popup
5. Criativo (texto e imagem)
6. Bot de aprovação e comandos
7. Publisher (Telegram + WhatsMiau.dev) e fila com ritmo
8. Orquestração (`run`), operação no Windows e README
9. Validação: dry-run e entrada gradual

## 14. Fora do escopo (por enquanto)

VPS e Docker, IA de imagem e de texto, múltiplas contas de afiliado, outras lojas, métricas de clique próprias e painel web.

## 15. Riscos e pontos a verificar

- **Formato dos dados do portal e do Gerador de link:** mapeados em `docs/notes/portal-mapping.md`.
- **Frete grátis e Full:** sem fonte por enquanto (ver a seção 6).
- **WhatsMiau.dev:** confirmar no primeiro teste o envio para JID de grupo e se `media` aceita base64.
- **Termos do ML:** mesmo com uma sessão real e ritmo humano, automação pode contrariar os termos. O freio automático e o volume baixo reduzem, mas não eliminam, o risco.
- **WhatsApp:** risco de restrição do número, que depende do volume e do tamanho dos grupos. Manter o ritmo moderado e aquecer os grupos aos poucos.
- **Computador desligado ou suspenso:** sem posts nesse período (aceito pelo usuário ao optar por não usar VPS).
