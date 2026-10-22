# Mapeamento do portal de afiliados do ML

**Fonte:** HAR gravado no Brave em 2026-10-22 (`data/har/portal.har`, fora do Git).
**Fixtures:** `tests/fixtures/portal/`, geradas com `har-extract --mask "<tag>=minhatag"`, sem cookies nem headers e com URLs privadas mascaradas.

> **Acentos:** o próprio DevTools gravou os corpos das buscas com acentos perdidos (`Ver�o`). Isso só afeta as fixtures. A extensão lê a resposta direto na página, já decodificada corretamente.

## 1. Lista de ofertas: `hub/search`

`POST https://www.mercadolivre.com.br/affiliate-program/api/hub/search?is_affiliate=true&device=desktop`

```json
{"search": "", "sort": "relevance", "filters": [], "offset": 18}
{"search": "", "sort": "relevance", "filters": [{"id": "category", "value": "MLB1384", "name": "Bebês"}], "offset": 0}
```

- **Paginação:** de 18 em 18 por `offset`. Com filtro de categoria, a página 1 (`offset: 0`) também vem por esta chamada.
- **Filtros** (vêm em `response.filters`):
  - `category`: 24 categorias raiz, com ids iguais aos da árvore do ML (`MLB1574` Casa, `MLB1648` Informática, `MLB1051` Celulares, `MLB1071` Pet Shop…).
  - `extra_commission` e `best_seller`: o formato do valor no pedido ainda não foi observado.
- **Ordenação:** `relevance`, `lowest_price` e mais uma.
- **Headers:** exige `x-csrf-token` (e `x-custom-origin`), gerados pela página. Por isso as chamadas precisam sair **de dentro da aba do portal**, nunca do backend.

### Oferta (`polycard_client_model.polycards[]`)

| Dado | Onde está | Observações |
|---|---|---|
| MLB do item | `metadata.id` | é o `itemId` usado no `createLink` |
| Tipo | `metadata.type` | `product` ou `user_product`; vai no `createLink` |
| URL | `"https://" + metadata.url` | `/p/MLB…` (produto) ou `/up/MLBU…`; é a `urls[0]` do `createLink` |
| Comissão extra | `metadata.extra_commission` (`"true"`/`"false"`) | vai como `extraCommission` no `createLink` |
| Título | componente `title` → `title.text` | |
| Comissão % | componente `affiliates_commission_chip` | **2 formatos:** `pill.text == "{ganancia} {extra}"` com o % em `chip.label.text` (`"17%"`, ganhos extras), ou `pill.text == "GANHOS 12%"` |
| Preço atual | `price.current_price.value` | |
| Preço anterior | `price.previous_price.value` | ausente quando não há desconto |
| Rótulo de desconto | `price.discount_label.text` | `"54% OFF"`, ou **`"34% OFF no Pix"`**: o desconto vale só no Pix |
| Avaliação | `review_compacted.values[key=label].label.text` | `"4.8"`; o componente some quando não há avaliações |
| Vendidos | `review_compacted.values[key=label2].label.text` | `"| +100 vendidos"`, `"| +5mil vendidos"` |
| Foto | `pictures.pictures[0].id` | maior versão: `https://http2.mlstatic.com/D_NQ_NP_2X_<id>-F.webp` (testado: 74 KB) |
| Destaque | componente `highlight` → `highlight.text` | `MAIS VENDIDO`, `MAIS BUSCADO`, `OFERTA IMPERDÍVEL`… |
| Internacional | presença do componente `cbt` | compra internacional |
| **Categoria** | **não vem na oferta** | sai do filtro `category` do próprio pedido |
| **Frete grátis / Full** | **não vem na lista** | ver a seção 4 |

No HAR, 197 ofertas em 12 páginas: comissão de 5% a 17% e 96 com "ganhos extras".

## 2. Link de afiliado: `createLink`

`POST https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink` (com o header `x-csrf-token`)

```json
{
  "itemId": "MLB5790540954",
  "type": "product",
  "extraCommission": "true",
  "itemAddToList": "MLB5790540954",
  "tag": "<sua tag de afiliado>",
  "urls": ["www.mercadolivre.com.br/<slug>/p/MLB53879960"],
  "buyBoxWinner": "MLB5790540954"
}
```

Resposta: `urls[0].short_url = "https://meli.la/33zyUam"`. Também traz `regex` (`"QL81M2-HWKB"`), o código para colar no buscador do app, e `total_error`.

- **Formato do link: `https://meli.la/<id>`**, e não `mercadolivre.com/sec/...` como os guias de terceiros diziam. A validação do backend precisa aceitar esse formato.
- **Efeito colateral:** `itemAddToList` coloca o produto numa lista de desejos do afiliado. O portal faz o mesmo quando o link é gerado à mão.
- **`tag`:** a etiqueta de afiliado da conta. Vai para o `.env` (`ML_AFFILIATE_TAG`) ou é capturada das chamadas da própria página.

## 3. Estratégia da extensão (derivada do mapeamento)

- **Token CSRF:** o wrapper de `fetch`/XHR (world MAIN) já vê os headers das chamadas da página. Ele guarda o último `x-csrf-token` (e `x-custom-origin`) e os reaproveita nas chamadas da extensão. Se o token expirar (401/403), a aba é recarregada uma vez; se falhar de novo, o freio é acionado.
- **Coleta:** só a leitura passiva não cobre a página 1 nem os filtros por categoria. Proposta: a extensão chama `hub/search` de dentro da aba, para cada categoria dos nichos, com 2 a 3 páginas por categoria e 5 a 15 s entre chamadas, a cada ~20 min. São as mesmas chamadas que a página faz quando a pessoa rola a lista ou troca o filtro. *(Pendente de aprovação: muda a seção 6 da spec.)*
- **Link:** `createLink` com o corpo acima, montado a partir dos dados da oferta guardados no backend (`itemId`, `type`, `extraCommission`, URL).

## 4. Pendências

- **Frete grátis e Full** não vêm no portal, e a API pública `/items` responde 403 sem login de desenvolvedor. Opções: tirar os dois critérios do ranking, consultar a página do produto só das ofertas pré-aprovadas, ou criar um app de desenvolvedor no ML e usar a API oficial com token. *(Decisão do usuário.)*
- **Desconto só no Pix:** o texto e o card precisam dizer "no Pix" quando `discount_label` contém "Pix".
- **Ofertas internacionais (`cbt`):** filtro opcional por nicho.
- **Formato de `extra_commission` e `best_seller` no pedido:** só se formos usar esses filtros.
