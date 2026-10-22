# Grupo Achadinhos das Noivas: descrição, boas-vindas, enquetes e nicho

Tudo o que fica dentro do grupo. Os números de frequência saem do `config.yaml` em produção:
`whatsapp_pacing` com até 10 posts por dia, entre 08:00 e 18:00, um a cada 75 ± 15 min.
Se mudar o config, mude o texto também.

## 1. Descrição do grupo

Limite do WhatsApp: 2.048 caracteres. O texto abaixo tem cerca de 900. Troque `[LINK DO KIT]`
pelo link da isca (ver [iscas-planilhas.md](iscas-planilhas.md)).

```text
💍 Achadinhos das Noivas ❤️

Ofertas garimpadas a dedo para quem vai casar (e para quem já casou e está montando a casa):
🍳 cozinha e chá de panela
🛏️ cama, mesa e banho
🔌 eletros da lista de presentes
💄 beleza e skincare da noiva
🎀 decoração, festa e lembrancinhas
✈️ lua de mel
🏡 casa nova

📌 Como funciona
• Até 10 achadinhos por dia, só entre 8h e 18h. Nada de madrugada.
• 1 enquete por semana para você escolher o que quer ver aqui.
• Só os admins postam. Zero spam, zero corrente, zero "bom dia" de 200 pessoas.
• Antes de postar, conferimos o histórico de preço: se a "promoção" é preço inflado, não entra.

🎁 Presente de boas-vindas: Kit Noiva Organizada (planilha de orçamento, checklist do
enxoval e lista de chá de panela pronta) 👉 [LINK DO KIT]

ℹ️ Os links são de afiliado do Mercado Livre: se você comprar, ganhamos uma pequena comissão
e você não paga nada a mais. Preço e estoque podem mudar a qualquer momento. Confira no app
antes de fechar.

💌 Indique para sua madrinha, sua mãe e a amiga que também está noiva!
```

Dá para mandar o texto pela API: a WhatsMiau tem `POST /group/updateGroupDescription/{instance}`
com `{"groupJid": "...", "description": "..."}`. Para um texto que muda pouco, colar no app é
mais simples.

## 2. Mensagem de boas-vindas fixada

O WhatsApp não manda boas-vindas automáticas em grupo. A mensagem fixada faz esse papel: é a
primeira coisa que quem entra vê. O pin dura no máximo 30 dias, então **fixe de novo todo
mês**. A WhatsMiau não tem rota para fixar, então isso é manual. Fixe também a enquete da
semana, se quiser destacá-la.

```text
👰‍♀️ Bem-vinda ao Achadinhos das Noivas! ❤️

Que bom ter você aqui! Este grupo existe para você montar o casamento e a casa nova gastando
menos.

🎁 Seu presente: o *Kit Noiva Organizada*
📊 Planilha de orçamento do casamento
✅ Checklist do enxoval por cômodo
🫖 Lista de chá de panela pronta, por faixa de preço
👉 [LINK DO KIT]

📌 Regras rapidinhas
1. Só os admins postam, para o grupo não virar bagunça.
2. Até 10 ofertas por dia, das 8h às 18h. Silencie à vontade, você não perde nada.
3. Toda semana tem enquete: vote, porque é ela que decide o que aparece aqui.
4. Preço e estoque mudam rápido. Confira no app antes de comprar.
5. Links de afiliado: você não paga nada a mais e ajuda o grupo a continuar existindo. 💕

💍 Conta pra gente: quando é o seu casamento? Responde a enquete fixada!

📲 Conhece outra noiva? Manda o link do grupo pra ela: [LINK DO GRUPO OU REDIRECIONADOR]
```

## 3. Enquetes semanais (automáticas)

**O que a WhatsMiau permite** (documentação e repositório `verbeux-ai/whatsmiau` lidos em
22/10/2026):

- **Enviar enquete:** sim, `POST /message/sendPoll/{instance}` com `number`, `name`, `values`
  (2 a 12) e `selectableCount`.
- **Receber votos:** a documentação diz que o voto chega pelo webhook, mas não mostra o
  formato nem lista um evento próprio de enquete. O código lê os formatos mais prováveis e
  guarda o que não entender para ajuste. Veja "Enquete semanal" em
  [operacao.md](../../operacao.md).
- **Fixar mensagem:** não existe rota para isso.

**O que foi implementado** (`src/ofertinhas/polls.py`):

- Liga no nicho com `polls: {weekday: qua, at: "12:30"}`. Já está assim no `config.yaml`
  local: quarta, no almoço, dentro da janela do grupo.
- 16 perguntas em rodízio, cerca de 4 meses sem repetir. Antes de cada nova, o resultado da
  anterior chega no Telegram do admin.
- O resultado também sai em `GET /admin/polls`. A rota `POST /admin/poll-now?niche=noivas`
  manda a próxima enquete na hora.

**Para que serve cada enquete** (use as respostas para decidir conteúdo, anúncios e o Ceremony):

| Chave | Pergunta (resumo) | O que a resposta decide |
|---|---|---|
| `data` | Quando é o grande dia? | Fase da base e quando ela começa a sair do grupo; criar o grupo "casa nova" |
| `achados` | Que achadinhos quer ver? (múltipla) | Pesos do nicho e `required_keywords` |
| `fase` | Fase do planejamento | Que isca e que conteúdo empurrar |
| `lista` | Lista de presentes física ou PIX | **Lead do Ceremony** (lista em PIX) |
| `convidados` | Quantos convidados | Tamanho de orçamento e perfil |
| `cha` | Vai ter chá? | Campanha de chá de panela e lista pronta |
| `preco` | Faixa de preço que mais compra | `min_price` e `max_price` do nicho |
| `site` | Vão ter site do casamento? | **Lead do Ceremony** |
| `casa` | Como está a casa nova | Peso de móveis e eletro em relação a beleza |
| `orcamento` | Orçamento total | Perfil de ticket e Ceremony Plus |
| `estilo` | Estilo do casamento | Temas de decoração e de criativos |
| `lua_de_mel` | Destino | Campanha de malas e praia |
| `dor` | O que tira o sono | Novas iscas e conteúdo |
| `horario` | Quando vê as ofertas | `whatsapp_pacing.window` |
| `black_friday` | O que vai caçar na BF (múltipla) | Prioridade da campanha da BF |
| `conteudo` | O que mais ajudaria | Equilíbrio entre conteúdo e ofertas |

Para a Black Friday, adiante a enquete `black_friday`: rode `poll-now` na semana de 9/11.

## 4. Validação do nicho por fase da noiva

Teste feito em 22/10/2026 com `POST /admin/niche-preview` em produção: 14 dias, 853 ofertas
coletadas, 280 nas categorias do nicho.

| Fase | Ofertas que entraram | Leitura |
|---|---:|---|
| Beleza pré-casamento | 45 | Bem coberta |
| Casa nova, móveis e decoração | 35 | Bem coberta |
| Eletro da lista de presentes | 26 | Coberta, mas quase tudo cai na regra de comissão |
| Cozinha e chá de panela | 25 | Coberta |
| Moda, madrinha, joias e noite | 24 | Coberta (inclui relógio feminino) |
| Cama, mesa e banho | 3 | **Pouca oferta chegando** |
| Lua de mel e viagem | 3 | **Pouca oferta chegando** |
| Festa, lembrancinha e convite | ~1 | **Quase nada chegando** |

**Conclusões:**

1. **O nicho já vai muito além de cozinha.** Os termos cobrem todas as fases. Acrescentei 34
   termos ao `config.yaml` local, entre eles `legging*`, `massageador*`, `necessaire*`,
   `oculos de sol`, `centro de mesa`, `kit madrinha`, `protetor de colchao` e `faca*`. Também
   bloqueei `ring light`, `drone` e `tripe`, que entravam por `iluminador*` e `bolsa*`. Com a
   lista nova, o teste foi de 166 para 171 ofertas no nicho (23 automáticas e 37 para aprovar).
2. **Pôr mais categorias não compensa.** Câmeras (por `instax`) e Saúde trouxeram filme
   fotográfico e vitamina com 5% de comissão. Ficaram de fora.
3. **O gargalo é a oferta que chega, não o filtro.** A coleta lê 1 página (18 ofertas) por
   categoria raiz, ordenada pelo portal. Cama, mesa e banho, lembrancinhas e lua de mel
   raramente estão no topo de "Casa" ou "Festas". O `hub/search` do portal aceita o campo
   `search` (ver `docs/notes/portal-mapping.md`). Coletar por termo de busca do nicho
   (`jogo de cama`, `lembrancinha casamento`, `mala de viagem`) resolveria isso. Essa
   mudança fica na extensão e merece um trabalho separado.
4. **A regra de desconto e comissão descarta 2 de cada 3 ofertas** (111 de 171). Em 14 dias
   saíram só 23 automáticas, menos de 2 por dia, contra uma cota de 10. Para encher o grupo,
   aprove mais cards no Telegram ou afrouxe o `review` do nicho (por exemplo, desconto de 25%
   e comissão de 12%).

O `config.yaml` não vai para o Git. As mudanças só valem no próximo `python deploy.py`.
