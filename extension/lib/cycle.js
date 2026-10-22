// Ciclo de coleta e passo de geração de link, sem depender das APIs do navegador:
// quem chama injeta `inTab` (executa a chamada dentro da aba do portal), `backend`, relógio e
// sono. Assim a lógica é testada em node e o service worker só faz a ligação.

import { detectBlock } from "./block.js";
import { buildSearchBody, cardCount, randomBetween } from "./portal.js";
import { withinWindow } from "./schedule.js";

const RECOVERABLE_STATUS = new Set([401, 403]);

function blockOf(result, url) {
  if (result.error === "no-csrf") return "csrf";
  return detectBlock({
    url: result.location || url,
    status: result.status,
    html: result.captcha ? "g-recaptcha" : undefined,
  });
}

function recoverable(reason, result) {
  return reason === "csrf" || (reason === "http" && RECOVERABLE_STATUS.has(result.status));
}

/**
 * Chama `inTab` e, se a resposta indicar token vencido (401/403) ou ausente, recarrega a aba
 * uma única vez por ciclo (`state.reloaded`) e tenta de novo.
 */
async function callWithRecovery(inTab, reloadTab, state, kind, url, body) {
  let result = await inTab(kind, url, body);
  let reason = blockOf(result, url);
  if (reason && recoverable(reason, result) && !state.reloaded) {
    state.reloaded = true;
    await reloadTab();
    result = await inTab(kind, url, body);
    reason = blockOf(result, url);
  }
  return { result, reason };
}

/** Buscas do ciclo: as categorias e depois os termos (`searches`, sem filtro de categoria). */
function searchTargets(cfg) {
  return [
    ...cfg.categories.map((category) => ({ category, search: "" })),
    ...(cfg.searches ?? []).map((search) => ({ category: null, search })),
  ];
}

function gate(cfg, now, ignoreWindow = false) {
  if (cfg.paused) return "paused";
  if (!ignoreWindow && !withinWindow(now, cfg.window)) return "outside";
  return null;
}

/** `ignoreWindow`: coleta pedida pelo usuário ("Coletar agora") vale a qualquer hora. */
export async function runCollection({
  cfg, backend, inTab, reloadTab, sleep, now, rng = Math.random, ignoreWindow = false,
}) {
  const closed = gate(cfg, now(), ignoreWindow);
  if (closed) return { status: closed };

  const state = { reloaded: false };
  const totals = { offers: 0, newOffers: 0, requests: 0, errors: 0 };
  for (const { category, search } of searchTargets(cfg)) {
    for (let pageIdx = 0; pageIdx < cfg.pages_per_category; pageIdx++) {
      if (totals.requests > 0) await sleep(randomBetween(cfg.request_gap_s, rng) * 1000);
      const body = buildSearchBody(category, pageIdx * cfg.page_size, search);
      const { result, reason } = await callWithRecovery(
        inTab, reloadTab, state, "search", cfg.search_url, body,
      );
      totals.requests++;
      if (reason) return { status: "blocked", reason, url: result.location, ...totals };
      if (result.status !== 200) {
        totals.errors++;
        break;
      }
      const out = await backend.post("/ext/raw", {
        url: cfg.search_url,
        request_body: body,
        status: result.status,
        body: result.json,
      });
      totals.offers += out?.parsed ?? 0;
      totals.newOffers += out?.new ?? 0;
      if (cardCount(result.json) < cfg.page_size) break; // acabou a categoria ou o termo
    }
  }
  return { status: "ok", ...totals };
}

export async function runLinkStep({ cfg, backend, inTab, reloadTab = async () => {}, limiter, nextLinkAt, now, rng = Math.random }) {
  const at = now();
  const closed = gate(cfg, at);
  if (closed) return { status: closed, nextLinkAt };
  if (at.getTime() < nextLinkAt) return { status: "wait", nextLinkAt };
  if (!limiter.canProceed()) return { status: "limit", nextLinkAt };

  const { request } = await backend.get("/ext/link-requests");
  if (!request) return { status: "idle", nextLinkAt };

  const { result, reason } = await callWithRecovery(
    inTab, reloadTab, { reloaded: false }, "createLink", request.url, request.body,
  );
  if (reason) return { status: "blocked", reason, url: result.location, nextLinkAt };

  const report = result.status === 200
    ? { mlb_id: request.mlb_id, response: result.json }
    : { mlb_id: request.mlb_id, error: result.error || `HTTP ${result.status}` };
  const out = await backend.post("/ext/links", report);
  limiter.record();
  return {
    status: "done",
    ok: Boolean(out?.ok),
    mlbId: request.mlb_id,
    nextLinkAt: at.getTime() + randomBetween(cfg.link_gap_s, rng) * 1000,
  };
}
