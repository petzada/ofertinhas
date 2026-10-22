# Slideshows de achadinhos para Reels, TikTok e carrossel

Estrutura para gerar as imagens no GPT Image ou no Nano Banana (Gemini) e postar como
slideshow. Público: noivas e mulheres de 22 a 40 anos montando casa.

## 1. Formato e specs

| Onde | Formato | Tamanho | Slides |
|---|---|---|---|
| TikTok, modo foto | Carrossel nativo com música | 1080 × 1920 (9:16) | Até 35. O ideal fica entre 5 e 9 |
| Instagram, carrossel | Feed | 1080 × 1350 (4:5) | Até 20. O ideal fica entre 6 e 10 |
| Instagram Reels | Fotos em sequência como vídeo, 1,5 a 2,5 s cada | 1080 × 1920 | 6 a 10 |

**Uma arte para os dois:** gere em 1080 × 1920 e mantenha texto e produto no **miolo de
1080 × 1350** (cerca de 285 px livres em cima e embaixo). O mesmo arquivo serve ao TikTok
inteiro e ao Instagram recortado em 4:5. A interface do TikTok cobre o rodapé (legenda e
botões) e a lateral direita, então deixe essas áreas sem texto.

Use carrossel nativo, não um vídeo montado de fotos com voz sintética. Guias de mercado de
2026 dizem que o TikTok trata os dois de forma diferente, e o nativo tem melhor alcance de
salvamento. Use música em alta, com volume baixo.

## 2. Esqueleto que funciona (5 a 9 slides)

| Slide | Papel | Regras |
|---|---|---|
| 1. **Gancho** | Para a rolagem em 1 segundo | Até 8 palavras, número ou contraste, a cena mais bonita. Escreva por último |
| 2. **Promessa** | Diz o que vem | "Salva pra não perder" e o critério ("todos abaixo de R$ 100") |
| 3 a 7. **Achados** | Um produto por slide | Foto real do produto, nome curto, benefício em 4 a 6 palavras e "por menos de R$ X" |
| 8. **Prova ou virada** | Credibilidade | "Eu confiro o histórico de preço antes de indicar" ou um antes e depois |
| 9. **CTA** | Leva ao grupo | "Os links estão no grupo Achadinhos das Noivas 💍, link na bio" ou "comente NOIVA" |

**Legenda:** a primeira linha repete o gancho, depois três linhas de contexto, o CTA e 3 a 5
hashtags de nicho: `#noivas2027`, `#chadepanela`, `#enxoval`, `#achadinhos`,
`#casamento`, `#casanova`. Coloque `#publi` ou "links de afiliado" quando houver link de
afiliado (CONAR, transparência de publicidade).

## 3. Ganchos (slide 1)

**Lista e número:**
- "Montei meu chá de panela inteiro com menos de R$ 50 por item"
- "7 itens de enxoval que ninguém te conta que vai precisar"
- "Os 5 eletros que mais aparecem nas listas de presente (e onde estão mais baratos)"
- "Enxoval completo de cama por menos de R$ 300?"

**Contraste e erro:**
- "Não coloque isso na sua lista de presentes 🚫 (coloque isto)"
- "Comprei caro antes de casar pra você não precisar"
- "Noiva, para de pagar R$ 200 em [item]"

**POV e identificação:**
- "POV: você acabou de ficar noiva e abriu a planilha de orçamento 😵"
- "Coisas que fazem uma casa de recém-casados parecer de revista"
- "O que eu compraria se fosse casar em 2027"

**Prova e dinheiro:**
- "Conferi o preço de 30 dias: estes estão realmente baratos"
- "Black Friday das Noivas: só o que caiu de verdade"

## 4. Séries prontas (cada uma rende várias semanas)

1. **Chá de panela por faixa de preço:** até R$ 30, até R$ 50, até R$ 100. Um post por faixa.
2. **Enxoval por cômodo:** cozinha, quarto, banheiro, lavanderia, sala.
3. **Lista de presentes inteligente:** eletros por categoria, "a que vale a pena e a que não".
4. **Beleza da noiva em contagem regressiva:** 90, 60, 30 e 7 dias antes (skincare, cabelo,
   unhas).
5. **Mala da lua de mel:** praia e cidade, "o que levar e o que comprar lá".
6. **Mesa posta do casal:** sousplat, taças, jogo americano, "mesa de revista gastando pouco".
7. **Madrinhas:** vestido e acessórios, caixa-convite para madrinha.
8. **Casa nova em 10 achados:** organização, decoração e cheirinho de casa.
9. **Erros de enxoval:** "comprei e não usei" contra "não vivo sem".
10. **Black Friday das Noivas:** ver [black-friday-das-noivas.md](black-friday-das-noivas.md).

## 5. Prompts para gerar as imagens

**Regra que não dá para quebrar:** o produto mostrado tem que ser **o produto real do
anúncio**. Imagem de IA de um produto que não é o do link é propaganda enganosa (CDC, art. 37)
e gera devolução e denúncia. Use a IA para cena, fundo, layout e tipografia. O produto entra
pela foto real do anúncio. A mesma foto que o card do Python usa é aceita pelo Nano Banana ou
pelo GPT Image como imagem de referência ("coloque este produto, sem alterá-lo, nesta cena").
Preço e texto miúdo: confira sempre, porque a IA erra números. Se preferir, gere a arte sem
texto e escreva no Canva ou no CapCut.

**Estilo base (cole no começo de todo prompt):**

```text
Fotografia editorial lifestyle, luz natural suave de janela, paleta rosé, nude, off-white e
dourado discreto (rosé #B5677A, como a marca do grupo), estética clean de revista de
casamento, formato vertical 9:16 1080x1920, deixe a faixa central livre e legível, sem
marcas d'água, sem logos de terceiros.
```

**Slide 1, gancho:**

```text
[estilo base] Cena: bancada de cozinha clara de um apartamento de recém-casados, com
[3 produtos da série] arrumados de forma bonita, flores brancas e alianças discretas ao fundo,
leve desfoque. Texto grande no centro, fonte serifada elegante, branco com sombra suave:
"[GANCHO]". Espaço vazio nas bordas superior e inferior.
```

**Slide de produto (com a foto real anexada):**

```text
[estilo base] Use EXATAMENTE o produto da imagem anexada, sem mudar cor, formato, marca ou
detalhes. Coloque-o em [cena: mesa posta, cama arrumada, banheiro de spa...] com luz
natural. No terço inferior do miolo, um cartão arredondado off-white com: "[NOME CURTO]" em
fonte serifada e "[BENEFÍCIO EM 5 PALAVRAS]" em fonte sem serifa menor. Sem preço.
```

**Slide de prova:**

```text
[estilo base] Mão feminina com aliança segurando o celular com um gráfico simples de preço
em queda (genérico, sem marca), fundo de sofá claro. Texto: "Eu confiro 30 dias de preço
antes de indicar ✅".
```

**Slide de CTA:**

```text
[estilo base] Flat lay de planner de casamento, caneta dourada, flores e celular mostrando
uma conversa de WhatsApp genérica, sem interface real. Texto: "Os links estão no grupo
💍 Achadinhos das Noivas", e embaixo, menor: "link na bio".
```

**Variações para não cansar:** troque a cena por cômodo, a paleta pela estação (verde-oliva
em casamento no campo, azul em praia) e o "rosto" por mão com aliança, vestido de noiva de
costas ou casal sem rosto. Evite rostos gerados por IA que pareçam pessoas reais.

## 6. Do grupo para o slideshow, em 15 minutos

1. Escolha no Telegram 4 a 6 ofertas da semana do nicho noivas (as que tiveram mais clique ou
   o melhor desconto conferido).
2. Baixe a foto do anúncio de cada uma. É a mesma que o card do Python usa.
3. Gere os slides com os prompts acima e escreva preço e texto final no Canva.
4. Poste no TikTok (modo foto) e no Instagram (carrossel 4:5, a mesma arte), e o melhor como
   Reels.
5. Não ponha link de afiliado no post: a conversão está no grupo. O post só leva ao grupo.

## 7. Link e CTA por rede

- **Instagram:** link na bio e automação "comente NOIVA e receba o link" (ManyChat ou a
  automação de DM da Meta). Comentário também aumenta o alcance.
- **TikTok:** link na bio. Conta pessoal exige um mínimo de seguidores e conta comercial
  costuma liberar antes; confira no app. Até lá, use "link no perfil do Instagram" ou "procura
  Achadinhos das Noivas no Insta".
- **Link do grupo:** use um link fixo seu que redirecione ao grupo com vaga (por exemplo,
  `seudominio/noivas?utm_source=tiktok`). Assim você mede de onde cada um vem e troca de grupo
  quando lotar (1.024 membros).

## 8. Ritmo e métrica

- **TikTok:** 1 slideshow por dia nas 3 primeiras semanas. Repostar o mesmo tema com outro
  gancho é normal e funciona.
- **Instagram:** 4 carrosséis por semana e 3 Reels feitos dos melhores carrosséis.
- **Métrica que importa:** salvamentos e compartilhamentos por post, e entradas no grupo por
  semana (cliques do link fixo). Curtida não importa.
