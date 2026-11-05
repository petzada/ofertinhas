# Campanha Meta Ads: entrada no grupo de achadinhos femininos

Objetivo: gente entrando no grupo do WhatsApp (nicho `mulher`: maquiagem, skincare, perfume, moda,
casa, utensílios e eletro). Pesquisa feita na Biblioteca de Anúncios da Meta em 05/11/2026, com
anúncios ativos no Brasil.

## O que a concorrência faz (Biblioteca de Anúncios)

Buscas: "grupo vip achadinhos whatsapp" (~2.600 anúncios ativos), "grupo vip maquiagem" (~480),
"grupo vip utilidades casa" (~490). Padrões que se repetem nos anunciantes que rodam há meses
(Achadinhos Dona Br desde maio, Garimpos da Isa, Tá em PROMO Mana, Casa verdinha com 10 anúncios
no mesmo criativo, Home das divas, Promos da Si para sua Casa, Deborah Indica):

1. **Destino é uma página, não o link do grupo.** Quase todos mandam para um site próprio ou um
   redirecionador (`*.lovable.app`, `redirecionador.buboflow.com.br`, `grupovip.economizando.org`)
   com um botão "Entrar no grupo". A página dispara o pixel (evento de conversão), o que permite
   otimizar para "entrou" e não só para clique, e distribui as pessoas entre grupos quando um
   enche (o WhatsApp limita o grupo a 1.024 pessoas).
2. **Texto em 3 tempos:** dor ("Pare de pagar caro nos seus produtos de beleza!"), o que tem no
   grupo, em lista com emoji (💄 maquiagem, ✨ skincare, 🏡 casa...), e a chamada "Entre
   gratuitamente / Clique em Saiba Mais". "Grupo VIP", "grupo secreto", "gratuito" e "antes de
   todo mundo" aparecem em quase todos.
3. **Criativo estático que funciona:** foto real de produtos em flatlay (maquiagem espalhada numa
   bancada) com uma faixa de texto curta por cima ("Grupo SECRETO com promoções de make"); print de
   conversa ou de grupo cheio de ofertas; mosaico de produtos com etiquetas de preço riscado.
4. **Voz de amiga** ("Amiga, se você ama make famosinha mas odeia pagar caro..."), em primeira
   pessoa, com a página no nome de uma pessoa ("Deborah Indica", "Garimpos da Isa").
5. Tem quem use "Comenta QUERO" para mandar o link por direct. Isso é para crescer perfil, não
   grupo; não vale para nós.

**Nosso diferencial, que ninguém mostra:** o sistema confere 30 dias de histórico de preço e
barra desconto inflado (`price_check`). "Só entra desconto de verdade: a gente confere o preço dos
últimos 30 dias" é um ângulo que os concorrentes não têm e que dá para provar.

## Estrutura da campanha

| Item | Configuração |
|---|---|
| Objetivo | **Leads** (ou Vendas), conversão no **site**, evento `Lead` disparado no clique do botão "Entrar no grupo" da página |
| Página de destino | `https://ofertinhas.marciopetigrosso.workers.dev/grupo` (rota do Worker, ver `docs/operacao.md`): botão para o grupo e Pixel com `Lead` no clique |
| Orçamento | Teste: R$ 40 a 60 por dia, por 7 dias, sem mexer nos primeiros 3 dias |
| Público | Mulheres, 22 a 55 anos, Brasil, público Advantage+ aberto (sem interesses no início). Excluir quem já está no grupo, se der para montar a lista |
| Posicionamentos | Advantage+ (Feed, Stories e Reels do Instagram e do Facebook) |
| Conjuntos | 1 conjunto com 6 criativos (o Advantage+ escolhe), ou 2 conjuntos por ângulo (beleza × casa) se quiser comparar |
| Texto principal | 3 variações (abaixo) |
| Título | "Grupo VIP gratuito de achadinhos" / "Só desconto de verdade" |
| Botão | Saiba mais |
| Métricas | Custo por `Lead` (clique em entrar), taxa de entrada real (membros novos ÷ leads), e saída do grupo em 7 dias |

**Antes de subir:** o grupo atual se chama "Achadinhos das Noivas". Renomeie e troque a foto e a
descrição para o público novo, senão quem chega pelo anúncio sai na hora.

## Textos (3 variações)

**A — dor + lista**
> 🚨 Pare de pagar preço cheio!
> No nosso Grupo VIP gratuito você recebe todo dia os melhores achadinhos do Mercado Livre:
> 💄 Maquiagem, skincare e perfumes
> 👗 Roupas, bolsas e acessórios
> 🍳 Utensílios e eletro pra cozinha
> 🏡 Cama, mesa, banho e decoração
> Toque em Saiba mais e entre antes que o grupo feche. 💖

**B — diferencial (preço conferido)**
> Sabe aquela "promoção" que era o mesmo preço mês passado? Aqui não entra.
> A gente confere o histórico de 30 dias de cada oferta antes de mandar no grupo. Só desconto de
> verdade: make, perfume, casa e eletro. Grupo gratuito, só ofertas, sem conversa. Toque em Saiba mais.

**C — voz de amiga**
> Amiga, eu caço oferta pra você não precisar. 🛍️
> Base, perfume, air fryer, jogo de panelas... quando cai de preço de verdade, vai pro grupo. É
> gratuito e silencioso: só ofertas, poucas por dia. Entra aqui 👇

## Prompts para os criativos estáticos

Formato: gere em **4:5 (1080×1350)** para o feed e repita em **9:16 (1080×1920)** para Stories e
Reels, deixando 250 px livres no topo e no fim. Gere a imagem sem texto e ponha o texto depois
(Canva ou Figma): os geradores ainda erram texto em português. Não use logos de marcas reais.

1. **Flatlay de maquiagem (o que mais roda)**
   > Top-down flat lay photo of assorted makeup products on a light marble vanity: eyeshadow palette,
   > lipsticks, blush compact, foundation bottle, brushes, a small perfume bottle, soft natural
   > window light, pastel pink and nude palette, unbranded packaging, realistic smartphone photo
   > style, empty space in the upper third for a text overlay, 4:5
   Texto por cima: **"Grupo VIP de make com desconto de verdade"** + selo "GRATUITO".

2. **Bancada de cozinha com eletro**
   > Bright modern Brazilian kitchen counter with a cream air fryer, a stand mixer, a ceramic
   > cookware set in beige and a few wooden utensils, morning sunlight, cozy and clean, unbranded
   > appliances, lifestyle photo shot on a phone, negative space on the left for text, 4:5
   Texto: **"Air fryer, panelas e eletro em promoção todo dia"**.

3. **Mosaico de achadinhos com etiquetas**
   > Grid collage of 6 product photos on soft pink background: perfume bottle, handbag, sandals,
   > cookware pot, bed linen set, skincare serum; each product on a white rounded card, clean
   > e-commerce style, unbranded, plenty of space for small price tags under each card, 4:5
   Depois, coloque em cada card "de R$ X por R$ Y" com preços **reais** de ofertas que passaram
   no grupo, e o título **"O que caiu no grupo essa semana"**.

4. **Celular com o grupo cheio de ofertas**
   > Close-up of a woman's hand with nude manicure holding a smartphone over a cozy bed with a
   > coffee mug, the phone screen is blank white (to be replaced), warm soft light, lifestyle,
   > shallow depth of field, 4:5
   Substitua a tela por um **print real** do grupo com 2 ou 3 cards de oferta (o card que o sistema
   desenha já serve). Texto: **"Receba no seu WhatsApp"**.

5. **Antes × depois do preço (diferencial)**
   > Minimalist split composition on a blush pink background, left side a shopping receipt
   > crumpled, right side a neat shopping bag with makeup and a small kitchen gadget peeking out,
   > soft studio light, playful and clean, unbranded, space for text on top, 4:5
   Texto: **"Promoção falsa não entra. Conferimos 30 dias de preço."**

6. **Pessoa real, voz de amiga**
   > Smiling Brazilian woman in her 30s sitting on a sofa holding a phone and a shopping bag,
   > casual home outfit, natural daylight in a cozy living room, authentic UGC style photo,
   > not overly retouched, space at the top for a caption, 4:5
   Texto: **"Eu caço oferta pra você 💖 Entra no grupo"**.

Evite prints falsos de depoimento ("depois que entrei economizei R$ 500") e descontos que não
existiram: a Meta reprova e o público percebe. Use só preços que de fato passaram no grupo.

## Ordem para subir

1. Renomear o grupo e ajustar foto e descrição.
2. Criar a página de destino com o botão e o Pixel (evento `Lead` no clique).
3. Gerar os 6 criativos e montar as 3 variações de texto.
4. Criar a campanha (Leads → site → `Lead`), conjunto com o público acima, e deixar **pausada** para
   revisar.
5. Publicar, esperar 3 dias sem mexer, depois cortar os criativos com custo por lead acima da média.
