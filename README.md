# Ofertinhas

![Status](https://img.shields.io/badge/status-em%20desenvolvimento%20ativo-brightgreen) ![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green) ![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white) ![Cloudflare Workers](https://img.shields.io/badge/Cloudflare-Workers-F38020?logo=cloudflare&logoColor=white)

Robô de ofertas de afiliado: **coleta, ranqueia e publica** promoções do Mercado Livre em grupos de **Telegram, WhatsApp e X**, com card gerado automaticamente e link de afiliado, para manter grupos de achadinhos ativos sem trabalho manual.

## Índice

- [Status do projeto](#status-do-projeto)
- [Demonstração](#demonstração)
- [Tecnologias utilizadas](#tecnologias-utilizadas)
- [Pré-requisitos e instalação](#pré-requisitos-e-instalação)
- [Como utilizar](#como-utilizar)
- [Publicação na nuvem](#publicação-na-nuvem)
- [Testes](#testes)
- [Contribuição](#contribuição)
- [Licença](#licença)
- [Autor e contato](#autor-e-contato)

## Status do projeto

🟢 **Em desenvolvimento ativo**: o sistema roda em produção na Cloudflare e recebe ajustes frequentes.

## Demonstração

O Ofertinhas tem três peças que trabalham juntas:

| Peça | Onde roda | Papel |
|---|---|---|
| **Backend** (API, bot, agendador, banco) | Worker Python `ofertinhas` na Cloudflare, com SQLite em Durable Object | Ranqueia as ofertas, desenha os cards, publica e envia avisos |
| **Extensão de navegador** | Brave no PC | Coleta as ofertas e gera os links de afiliado (o Mercado Livre bloqueia navegador automatizado) |
| **Agendador do Windows** | PC | Acorda o PC nos horários de coleta e mantém o navegador ativo |

**Principais funcionalidades**

- **Ranqueamento** por desconto, comissão e regras por nicho (`casa`, `tech`, `beleza`, `noivas`...), com palavras obrigatórias e bloqueadas.
- **Detecção de desconto inflado** (`price_check`): compara com o histórico de 30 dias e descarta "preço de" maquiado.
- **Cards com imagem e QR code** gerados com Pillow e hospedados no R2.
- **Publicação com ritmo próprio** por grupo: um grupo de Telegram com todos os nichos gerais e grupos de WhatsApp por nicho fino.
- **Aprovação pelo Telegram**: ofertas duvidosas chegam ao admin com botões para aprovar ou descartar.
- **Enquete semanal** nos grupos de WhatsApp, com resultado enviado ao admin.
- **Mensagem de status fixada** no chat do admin (08h, 13h e 20h) e alertas de estoque baixo de ofertas.
- **Coleta sob demanda**: quando a fila de um grupo fica curta, a nuvem pede uma coleta extra à extensão.

Operação completa em [`docs/operacao.md`](docs/operacao.md).

## Tecnologias utilizadas

- **Python 3.12+**: FastAPI, Uvicorn, APScheduler, python-telegram-bot, httpx, Pydantic, Pillow, qrcode
- **Cloudflare**: Python Workers, Durable Objects (SQLite), R2, Cron Triggers
- **Extensão de navegador** em JavaScript (Manifest V3)
- **Integrações**: Telegram Bot API, WhatsMiau (WhatsApp), API do X, Mercado Livre
- **Qualidade**: pytest (+ pytest-asyncio, respx, freezegun, pytest-testmon), Ruff, lefthook, GitHub Actions

## Pré-requisitos e instalação

**Pré-requisitos**

- **Python 3.12** ou superior
- **Node.js** (só para os testes da extensão)
- Navegador **Brave** (ou outro Chromium) para a extensão
- Contas: bot do Telegram (@BotFather), tag de afiliado do Mercado Livre e, opcionalmente, WhatsMiau, X e Cloudflare R2

**Instalação**

```bash
git clone https://github.com/petzada/ofertinhas.git
cd ofertinhas
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Linux/macOS: .venv/bin/python
.venv/Scripts/lefthook install
python -m ofertinhas setup                           # cria config.yaml, .env e a config da extensão
```

Preencha o `.env` (veja `.env.example`: tokens do Telegram, tag de afiliado, WhatsMiau, X e R2) e ajuste nichos e regras no `config.yaml` (modelo em `config.example.yaml`).

Para a extensão: abra `brave://extensions`, ative o modo de desenvolvedor, clique em **Carregar sem compactação** e escolha a pasta `extension/`. Gere o token que ela usa com `python -m ofertinhas new-token`.

## Como utilizar

```bash
python -m ofertinhas run              # API da extensão + bot + agendador (dev e plano B; recusa rodar com a nuvem no ar)
python -m ofertinhas api              # só a API local da extensão
python -m ofertinhas render-sample    # gera um card de exemplo do nicho
python -m ofertinhas whatsapp-groups  # lista grupos e JIDs da instância da WhatsMiau
python -m ofertinhas install-task     # inicia o backend ao fazer logon no Windows
python -m ofertinhas --help           # todos os comandos
```

Com `DRY_RUN=true` os posts vão só para o chat do admin (e o WhatsApp só para `WHATSAPP_TEST_JID`), ideal para testar sem atingir os grupos.

Antes de ligar um nicho novo, dá para simular quantas ofertas entrariam sem postar nada, pela rota `/admin/niche-preview` da nuvem (exemplo em [`docs/operacao.md`](docs/operacao.md)).

## Publicação na nuvem

O Worker é publicado pelo workflow `deploy.yml` a cada merge na `main` (`cloud/worker/deploy.py`). Segredos sobem com `python cloud/worker/push_secrets.py` e o webhook do Telegram/WhatsApp é configurado com `python cloud/worker/set_webhook.py`. Essas ações são do responsável pelo projeto.

## Testes

```bash
.venv/Scripts/python -m pytest                       # suíte Python completa
.venv/Scripts/python -m pytest --testmon             # só o que o diff afeta
node --test "extension/tests/**/*.test.js"           # testes da extensão
.venv/Scripts/python -m ruff check .                 # lint
```

Os testes usam mocks e `config.example.yaml`: não precisam de tokens reais nem de banco. No dia a dia, o **lefthook** formata e faz lint no commit e roda os testes afetados no push; o **GitHub Actions** roda o lint em todo PR e a matriz Python 3.12/3.13 + extensão quando o PR fica pronto.

## Contribuição

Contribuições são bem-vindas! Para propor uma melhoria:

1. Abra uma **issue** descrevendo o problema ou a ideia antes de começar algo grande.
2. Faça um **fork** e crie um branch a partir da `main`: `<tipo>/<nome-kebab>` (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`).
3. Use **commits semânticos** em português: `<tipo>(<escopo>): <descrição no imperativo>`.
4. Rode lint e testes antes de enviar (veja [Testes](#testes)).
5. Abra o **Pull Request** em *draft*, explicando o quê e o porquê. O merge é feito pelo autor.

Não inclua segredos (`.env`, chaves de API, tokens) em commits ou PRs.

Regras completas do fluxo de desenvolvimento em [`AGENTS.md`](AGENTS.md).

## Licença

Distribuído sob a licença **MIT**, de código aberto. Isso significa que você **pode** usar, copiar, modificar, mesclar, publicar, distribuir, sublicenciar e até vender cópias do código, inclusive em projetos comerciais, **desde que** mantenha o aviso de copyright e o texto da licença. O software é fornecido "no estado em que se encontra", **sem garantias**, e o autor não se responsabiliza por danos decorrentes do uso.

Texto completo em [`LICENSE`](LICENSE).

## Autor e contato

**Marcio Petigrosso** ("petzada"): idealização e desenvolvimento.

- GitHub: [@petzada](https://github.com/petzada)
- LinkedIn: [in/petigrosso](https://www.linkedin.com/in/petigrosso)
