# Kit de crescimento: Achadinhos das Noivas

Material para crescer o grupo de WhatsApp de noivas, montado em 22/10/2026.

| # | Pedido | Onde está |
|---|---|---|
| 1 | Descrição do grupo (o que é postado, quantas vezes por dia, sem spam) | [grupo-whatsapp.md §1](grupo-whatsapp.md#1-descrição-do-grupo) |
| 2 | Enquetes fixas e automáticas pela WhatsMiau, com coleta das respostas | [grupo-whatsapp.md §3](grupo-whatsapp.md#3-enquetes-semanais-automáticas) e o código em `src/ofertinhas/polls.py` (operação em [operacao.md](../../operacao.md)) |
| 3 | Estrutura de slideshows para Reels e TikTok, com prompts de imagem | [slideshows-reels-tiktok.md](slideshows-reels-tiktok.md) |
| 4 | Checklist do Pinterest | [pinterest.md](pinterest.md) |
| 5 | Estrutura das planilhas (orçamento, enxoval, chá de panela) e oferta com Meta Ads | [iscas-planilhas.md](iscas-planilhas.md) |
| 6 | Divulgação cruzada com o Ceremony | [ceremony-cruzada.md](ceremony-cruzada.md) |
| 7 | Black Friday das Noivas: grupo, Meta Ads, orgânico e ganchos do ano | [black-friday-das-noivas.md](black-friday-das-noivas.md) |
| 8 | Mensagem de boas-vindas fixada, com regras e isca | [grupo-whatsapp.md §2](grupo-whatsapp.md#2-mensagem-de-boas-vindas-fixada) |
| 9 | Validação das categorias por fase da noiva | [grupo-whatsapp.md §4](grupo-whatsapp.md#4-validação-do-nicho-por-fase-da-noiva) |

## Ordem sugerida (até a Black Friday)

1. **Esta semana:** subir o kit (as 3 planilhas), trocar a descrição e a fixada, ligar as
   enquetes (deploy + `push_secrets.py` + `set_webhook.py --whatsapp`), criar o link fixo do
   grupo com UTM.
2. **De 1 a 15/11:** Meta Ads com o Mapa da Black Friday (a maior verba fica aqui),
   slideshow diário, Pinterest.
3. **De 16 a 30/11:** reduzir os anúncios, apertar o orgânico e ajustar o volume do grupo para
   a semana da BF.

## Pendências fora deste kit

- **Link fixo do grupo** (redirecionador com UTM e troca de grupo quando lotar): ainda não
  existe. Pode ser uma rota no próprio Worker.
- **Coleta por termo de busca** no portal (`hub/search` com `search`), para trazer cama,
  mesa e banho, lembrancinhas e lua de mel, que quase não chegam hoje (ver a validação do
  nicho).
- **Fontes da pesquisa** (consultadas em 22/10/2026; quase tudo é blog de terceiros, não
  documentação oficial):
  [WhatsMiau docs](https://whatsmiau.dev/docs/getting-started),
  [repo verbeux-ai/whatsmiau](https://github.com/verbeux-ai/whatsmiau),
  [TikTok Photo Mode 2026 (instacarousel)](https://instacarousel.com/blog/tiktok-carousel-photo-mode-2026/),
  [Slideshow no TikTok (socialrails)](https://socialrails.com/blog/how-to-make-slideshow-on-tiktok),
  [Carrossel do TikTok Shop (carouscale)](https://www.carouscale.com/en/tiktok-shop-carousel),
  [Slideshow no TikTok Shop (moras.ai)](https://moras.ai/blog/tiktok-shop-slideshow-compliance),
  [Afiliados no Pinterest (pingenerator)](https://pingenerator.com/blog/pinterest-affiliate-marketing-guidelines),
  [Click-to-WhatsApp Ads 2026 (SocialHub)](https://www.socialhub.pro/blog/click-to-whatsapp-ads-2026/),
  [Black Friday 2026 e Procon (JB)](https://www.jb.com.br/editorias/2026/10/05/black-friday-2026-procon.html),
  [Desconto falso na Black Friday (Diário do Nordeste)](https://diariodonordeste.verdesmares.com.br/opiniao/colunistas/alberto-pompeu/black-friday-comeca-em-outubro-e-o-desconto-falso-tambem-1.3798653).
