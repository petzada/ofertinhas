# Divulgação cruzada: Achadinhos das Noivas × Ceremony

O Ceremony (ceremony.com.br) cria o site do casamento com RSVP e lista de presentes em PIX e
cartão. O grupo junta noivas que estão comprando. É o mesmo público no mesmo momento, e um
produto completa o outro.

## 1. A tese (sem um canibalizar o outro)

> **"Peça os presentes em PIX no site do casamento e compre você mesma o enxoval com desconto
> no grupo."**

- O **Ceremony** ganha com presente em dinheiro (taxa sobre o presente e os planos). Mandar o
  **convidado** para o Mercado Livre tiraria receita do Ceremony. Por isso, **o grupo não
  aparece para convidados nos sites dos casais.**
- O **grupo** ganha com a **noiva** comprando para a própria casa. O dinheiro que ela recebe
  no PIX vira compra de enxoval com desconto no grupo. Um alimenta o outro.

## 2. Claims que podem ser usados

Use só o que está aprovado em `ceremony/docs/marketing/claims-inventory.md`, revisado até
18/12/2026:

- "Site, RSVP e lista de presentes **grátis** para criar e publicar"
- "Pronto em **5 minutos**"
- "A menor taxa por presente do mercado: **2,99%**" (comparativo, com risco aceito pela
  D-LAND-002; confira antes de usar em anúncio pago)
- "100% personalizáveis"

Não use contagem de usuários, depoimentos públicos nem casos: o inventário proíbe nesta etapa.

## 3. Do grupo para o Ceremony

| Onde | O quê | Frequência |
|---|---|---|
| Enquetes `lista` e `site` | Quem marcar "PIX no site" ou "queremos fazer" é lead quente: na semana seguinte, o post explica o Ceremony | Quando a enquete sair |
| Post de conteúdo no grupo | "Lista de presentes em PIX: como funciona, quanto custa a taxa e como criar em 5 min", com link e `utm_source=grupo-whatsapp` | 1 a cada 2 semanas, nunca mais que 1 por semana |
| Kit Noiva Organizada | Rodapé em cada planilha e CTA na aba Convidados ("RSVP automático no Ceremony") | Sempre |
| Mensagem fixada e descrição | Uma linha: "Site do casamento grátis com RSVP e lista em PIX: [link]" | Opcional. Teste depois que o grupo passar de 300 membros |
| Black Friday | "Monte a lista em PIX antes do chá e use o dinheiro nas ofertas da BF" | Semana de 16/11 |

**Regra de convívio:** no máximo 1 post de Ceremony para cada 30 ofertas. O grupo existe pelas
ofertas. Se ele virar canal de anúncio da casa, as saídas sobem, e isso aparece na contagem de
saídas por post.

## 4. Do Ceremony para o grupo

| Onde (no Ceremony) | O quê | Observação |
|---|---|---|
| Fim do onboarding, depois de publicar o site | Card "Montando a casa? Entre no grupo Achadinhos das Noivas: ofertas conferidas para o enxoval" | Momento de maior satisfação; o casal já ganhou algo |
| Painel, área da lista de presentes | "Itens que vocês vão comprar sozinhos? Veja os achadinhos do grupo" | Só para o casal, nunca no site público |
| E-mails de campanha (`emails/campaign-*.tsx`) | Bloco de rodapé com o grupo e o kit | Só para quem aceitou e-mail de marketing (LGPD) |
| Blog ou SEO (`docs/SEO-CONTENT-PLAN.md`) | Posts "lista de chá de panela", "enxoval completo", "orçamento de casamento" com o kit como CTA | O kit é ótima isca de SEO |
| Página de obrigado do Plus/Ceremony | "Bônus: Kit Noiva Organizada e grupo de ofertas" | Benefício percebido sem custo |

## 5. Marca

- **Agora:** mantenha o grupo como marca própria ("Achadinhos das Noivas"), com o Ceremony
  como **parceiro** ("apoio: Ceremony"). Grupo de ofertas tem cara de varejo, e se o vínculo
  for forte demais pode baratear a marca do SaaS. Uma marca própria também pode crescer sozinha.
- **Depois de validar** (cerca de 1.000 membros e taxa de saída baixa): teste "Achadinhos
  das Noivas, uma comunidade Ceremony" e meça se o clique para o Ceremony sobe.

## 6. Medição

- **UTMs fixos:** `utm_source=grupo-whatsapp&utm_medium=post|fixada|kit&utm_campaign=<tema>`
  no link do Ceremony, e `utm_source=ceremony&utm_medium=onboarding|painel|email` no link fixo
  do grupo.
- **No Ceremony:** cadastros e sites publicados por `utm_source=grupo-whatsapp` (o
  `docs/LANDING-MEASUREMENT.md` já define a medição da landing).
- **No grupo:** entradas vindas do Ceremony pelo redirecionador e saídas na semana dos posts do
  Ceremony.
- **Cupom:** o catálogo não tem cupom hoje. Se for criar, um código exclusivo do grupo para o
  Plus (R$ 19,90) é o jeito mais limpo de medir conversão.

## 7. Cuidados

- **LGPD:** e-mail do Ceremony só para quem tem base legal de marketing. A lista do formulário
  de Meta Ads só serve ao Ceremony se o formulário disser isso.
- **Transparência:** no grupo, deixe claro que o Ceremony é do mesmo dono ou parceiro ("nosso
  site de casamento"). Indicação disfarçada queima a confiança dos dois.
- **Convidados:** nada de oferta de afiliado nos sites públicos dos casais.
