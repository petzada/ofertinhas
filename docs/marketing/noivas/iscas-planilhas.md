# Iscas: Kit Noiva Organizada (estrutura das planilhas e oferta)

Três entregáveis grátis que a pessoa recebe ao entrar no grupo. Aqui está o **esqueleto**
(abas, colunas e fórmulas) para você preencher o conteúdo depois. O pacote todo se chama
**Kit Noiva Organizada**.

**Formato recomendado:** Google Planilhas com link de cópia
(`https://docs.google.com/spreadsheets/d/<ID>/copy`). A pessoa clica e ganha a própria cópia,
você não recebe pedido de acesso, e no celular também funciona. Ofereça um `.xlsx` como
alternativa.

**Identidade:** rosé `#B5677A`, off-white, fonte Poppins (a mesma dos cards). Na primeira
aba, um bloco "Como usar" com 3 passos e o rodapé "Feito pelo grupo Achadinhos das Noivas 💍
[link]" e "Site do casamento com RSVP e lista em PIX: Ceremony [link]".

---

## 1. Planilha de orçamento do casamento

| Aba | Para quê |
|---|---|
| **Como usar** | 3 passos, legenda das cores, CTA do grupo e do Ceremony |
| **Resumo** | Painel: orçamento total, previsto, contratado, pago, falta pagar e gráfico por categoria |
| **Categorias** | Orçamento por categoria em % e R$ |
| **Fornecedores** | Comparação de orçamentos e o fornecedor escolhido |
| **Pagamentos** | Parcelas e vencimentos mês a mês |
| **Convidados** | Lista, lado, confirmação e mesa |
| **Cronograma** | O que fazer de 12 meses até 1 semana antes |

**Categorias.** Colunas: `Categoria | % sugerido | Previsto (R$) | Contratado (R$) |
Pago (R$) | Diferença`. Fórmulas: `Previsto = Resumo!Total * %`, `Diferença = Previsto -
Contratado`, formatação condicional vermelha se for negativa.
Linhas: local e recepção, buffet e bebidas, decoração e flores, foto e vídeo, música, traje
da noiva, traje do noivo, beleza (cabelo e maquiagem), convites e papelaria, lembrancinhas,
alianças, cerimonialista, documentação e cartório, lua de mel, imprevistos.
*(Os % são seu conteúdo. Deixe uma coluna "% sugerido" editável e avise que é referência.)*

**Fornecedores.** `Categoria | Fornecedor | Contato | Orçamento (R$) | O que inclui | Nota
(1–5) | Escolhido? (✓) | Contrato assinado? | Observações`. Use validação de dados para ✓ e
listas suspensas.

**Pagamentos.** `Fornecedor (lista) | Parcela | Valor | Vencimento | Pago? | Data do pagamento
| Forma`. Resumo por mês com `SOMASES(Valor; Vencimento; ">="&início; Vencimento; "<"&fim)`.
Destaque o que vence nos próximos 15 dias.

**Convidados.** `Nome | Lado (noiva/noivo/casal) | Grupo (família, amigos, trabalho) | Adultos
| Crianças | Convite enviado? | Confirmou? (sim/não/pendente) | Mesa | Restrição alimentar`.
Totais por status. **CTA nesta aba:** "Cansada de cobrar confirmação no WhatsApp? No Ceremony
o convidado confirma presença sozinho no site do casamento."

**Cronograma.** `Prazo (12m, 9m, 6m, 4m, 3m, 2m, 1m, 2 semanas, 1 semana) | Tarefa | Feito?`,
com barra de progresso (`CONT.SE(feito; VERDADEIRO) / CONT.VALORES(tarefa)`).

---

## 2. Checklist do enxoval por cômodo

| Aba | Para quê |
|---|---|
| **Como usar** | Prioridades, o que pedir na lista e o que comprar na promoção |
| **Cozinha**, **Quarto**, **Banheiro**, **Lavanderia**, **Sala**, **Eletros** | Um cômodo por aba |
| **Resumo** | % completo por cômodo e quanto falta gastar |

**Colunas de cada cômodo:** `Item | Quantidade sugerida | Prioridade (essencial, desejável,
luxo) | Faixa de preço | Preço-alvo de promoção (R$) | Já tenho? | Pedir na lista? |
Comprado? | Paguei (R$) | Onde (link do achadinho)`.

- **Preço-alvo de promoção:** é o diferencial do grupo. Vem do histórico de preços que o
  sistema já coleta (`price_history`, 30 dias). Preencha com "bom preço = abaixo de R$ X".
  Isso vira a base do **Mapa da Black Friday das Noivas** (ver
  [black-friday-das-noivas.md](black-friday-das-noivas.md)).
- **Pedir na lista?:** separa o que vai para a lista de presentes (e daí para o Ceremony,
  se for em PIX) do que a noiva compra sozinha nas ofertas do grupo.
- **Resumo:** `% completo = CONT.SE(Comprado ou Já tenho) / total de essenciais`, com barra
  por cômodo.

*(Os itens e as quantidades são seu conteúdo. Comece pelos essenciais: cerca de 25 na
cozinha, 12 no quarto, 10 no banheiro, 8 na lavanderia, 10 na sala e 12 eletros.)*

---

## 3. Lista de chá de panela pronta

| Aba | Para quê |
|---|---|
| **Como usar** | Como mandar aos convidados, como evitar presente repetido |
| **Lista pronta** | Itens por faixa de preço |
| **Quem vai dar** | Controle durante o chá |
| **Mensagem pros convidados** | Textos prontos para o WhatsApp |

**Lista pronta:** `Faixa (até R$ 30, R$ 30–60, R$ 60–100, R$ 100–150, acima de R$ 150) |
Item | Por que vale | Sugestão de modelo | Link do achadinho | Escolhido para minha lista?`.
Com o filtro "Escolhido", a noiva monta a lista dela em 5 minutos.

**Quem vai dar:** `Item | Convidado | Confirmado? | Chegou?`, com aviso de repetido via
`CONT.SE`.

**Mensagem pros convidados:** 2 ou 3 textos curtos ("Oi! Vou fazer meu chá de panela dia
__ e montei uma listinha com opções de todos os preços: [link]").

---

## 4. A oferta em cima do kit

**Promessa central:** "Kit Noiva Organizada **grátis**: planilha de orçamento, checklist do
enxoval e lista de chá de panela pronta. É só entrar no grupo Achadinhos das Noivas."

| Elemento | Texto |
|---|---|
| Para quem | Noivas que vão casar em 2026 ou 2027, de qualquer orçamento |
| Dor | "Não sei quanto vou gastar", "não sei o que comprar", "vou gastar demais no enxoval" |
| Ganho | Controle do orçamento em 10 minutos, enxoval sem esquecer nada, chá de panela pronto |
| Por que grátis | "O grupo se paga com as comissões das ofertas, e você não paga nada a mais" |
| Bônus | Acesso às ofertas conferidas e às enquetes que decidem o que entra no grupo |
| Urgência (BF) | "Entre antes da Black Friday e receba o Mapa da Black Friday das Noivas" |

**Entrega:** o link do kit fica na **mensagem fixada** e na **descrição** do grupo (ver
[grupo-whatsapp.md](grupo-whatsapp.md)). Assim, entrar no grupo é a condição natural para
receber.

## 5. Funil com Meta Ads

```text
Anúncio (Reels/Stories com o mockup do kit)
   → Formulário instantâneo da Meta (nome + e-mail + "quando é seu casamento?")
   → Tela de agradecimento: botão "Entrar no grupo e baixar o kit" (link fixo do grupo)
   → Grupo: mensagem fixada com o link do kit
```

**Por que o formulário instantâneo é o ponto de partida:** não precisa de site, e você fica
com o **e-mail** (público seu, que serve ao Ceremony e ao remarketing), além de saber a data
do casamento. O botão da tela final leva ao grupo.

**Alternativa para testar em seguida:** anúncio de clique para WhatsApp (objetivo Engajamento,
destino WhatsApp) para um número do **WhatsApp Business** com mensagem automática de saudação
que entrega o kit e o link do grupo. A conversa é mais barata, mas você não fica com o e-mail,
e o número precisa estar ligado à página. Não aponte o anúncio direto para o link de convite
`chat.whatsapp.com`: o comportamento e a política para isso não estão claros, e você perde a
medição.

**Estrutura da campanha de teste:**

- Objetivo **Cadastros** (formulário instantâneo), 1 campanha e 1 conjunto em Advantage+ com
  público aberto: mulheres de 22 a 40 anos, Brasil. Se ainda existirem no Gerenciador, teste
  um 2º conjunto com status de relacionamento "noivo(a)" ou o evento de vida "recém-noivos"; a
  Meta cortou muitos interesses e esses mudam de lugar. O criativo é que segmenta: "noiva" no
  primeiro segundo.
- **3 a 4 criativos:** (1) mockup do kit no celular, (2) slideshow "POV: acabei de ficar noiva
  e abri a planilha", (3) depoimento ou print do grupo (com autorização), (4) "chá de panela
  pronto em 5 minutos".
- **Verba:** R$ 30 a 50 por dia por 7 dias, sem mexer nos 3 primeiros dias.
- **Métricas:** custo por cadastro (CPL) e, principalmente, **custo por membro**: verba ÷
  entradas líquidas no grupo no período. Corte o criativo que estiver 2× acima da média depois
  de cerca de R$ 60 gastos nele.
- **Referência de custo:** não achei número confiável de CPL para noivas no Brasil. Um vendor
  cita cerca de R$ 5 por conversa de clique para WhatsApp em geral (SocialHub, 2026). Trate
  como chute inicial e meça o seu.

**LGPD:** no formulário, deixe explícito que o e-mail é para enviar o kit e novidades do grupo
(e do Ceremony, se for usar) e inclua o link da política de privacidade. A Meta exige esse link.
