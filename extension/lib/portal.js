// Formato das chamadas do portal de afiliados (ver docs/notes/portal-mapping.md).

/**
 * Corpo do POST hub/search; `category` é {id, name} ou null para a lista geral, e `search`
 * é o termo digitado na busca do portal ("" lista sem termo).
 */
export function buildSearchBody(category, offset, search = "") {
  return {
    search,
    sort: "relevance",
    filters: category ? [{ id: "category", value: category.id, name: category.name }] : [],
    offset,
  };
}

export function cardCount(json) {
  return json?.polycard_client_model?.polycards?.length ?? 0;
}

/** Inteiro entre [mínimo, máximo] (segundos), sorteado. */
export function randomBetween([low, high], rng = Math.random) {
  return low + Math.round(rng() * (high - low));
}
