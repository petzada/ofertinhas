// Texto do estoque no popup: quantas ofertas já têm link (a nuvem posta sozinha), quantas
// esperam a extensão gerar o link e quando dá para fechar o Brave.

const LINK_MINUTES = 1; // ~1 link por minuto com o portal aberto (intervalo de 30 a 90 s)

function hhmm(iso) {
  return new Date(iso).toLocaleTimeString("pt-BR", {
    hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo",
  });
}

/** Até quando o estoque dura, com e sem os links que ainda faltam. */
function until(stock) {
  const groups = stock.groups || [];
  const ends = groups.map((g) => g.ends_at).filter(Boolean).sort();
  const withLinks = groups.map((g) => g.ends_at_with_links).filter(Boolean).sort();
  const now = ends.length ? `até ${hhmm(ends[0])}` : "o resto do dia";
  if (!stock.waiting_links) return now;
  const later = withLinks.length ? `até ${hhmm(withLinks[0])}` : "o resto do dia";
  return later === now ? now : `${now} (${later} com os links)`;
}

/**
 * @param {{ready: number, waiting_links: number, groups: object[]}} stock resposta de /ext/stock
 * @param {{collecting?: boolean, paused?: boolean}} extension estado da extensão
 * @returns {{ready: string, waiting: string, until: string, note: string, tone: string}}
 */
export function describeStock(stock, { collecting = false, paused = false } = {}) {
  const waiting = stock.waiting_links || 0;
  let note;
  let tone;
  if (paused) {
    note = "Extensão pausada: os links não estão sendo gerados.";
    tone = "bad";
  } else if (collecting) {
    note = "Coletando ofertas… mantenha o Brave aberto.";
    tone = "warn";
  } else if (!waiting && !stock.ready) {
    note = "Sem estoque: clique em Coletar agora e deixe o Brave aberto.";
    tone = "bad";
  } else if (waiting) {
    note = `Gerando links: faltam ${waiting} (~${waiting * LINK_MINUTES} min). Mantenha o Brave aberto.`;
    tone = "warn";
  } else {
    note = "✅ Estoque abastecido. Pode fechar o Brave.";
    tone = "ok";
  }
  return {
    ready: String(stock.ready || 0),
    waiting: String(waiting),
    until: until(stock),
    note,
    tone,
  };
}
