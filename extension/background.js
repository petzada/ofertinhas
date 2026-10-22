// Service worker da extensão: liga a lógica de lib/ às APIs do navegador.
// - alarme "collect": um ciclo de coleta, reagendado com variação aleatória;
// - alarme "links": a cada 30 s, no máximo um link de afiliado (e a coleta pedida pela nuvem,
//   `collect_now`, quando o estoque está curto);
// - freio: qualquer sinal de bloqueio pausa tudo e avisa o backend (que avisa no Telegram).

import { Backend } from "./lib/backend.js";
import { runCollection, runLinkStep } from "./lib/cycle.js";
import { postInPage } from "./lib/inpage.js";
import { RateLimiter } from "./lib/ratelimit.js";
import { nextDelayMs, shouldCollectNow } from "./lib/schedule.js";
import { TabGate } from "./lib/tabgate.js";

const DEFAULT_BACKEND = "http://127.0.0.1:8765";
const MIN_GAP_BETWEEN_CALLS_MS = 3_000;
const PORTAL_PREFIX = "https://www.mercadolivre.com.br/afiliados/hub";
const CSRF_WAIT_MS = 15_000;
const RETRY_AFTER_ERROR_MS = 5 * 60_000;

// --- armazenamento ----------------------------------------------------------

/** config.local.json, gerado por `python -m ofertinhas setup` (fica fora do Git). */
async function localConfig() {
  try {
    const response = await fetch(chrome.runtime.getURL("config.local.json"));
    return response.ok ? await response.json() : {};
  } catch {
    return {};
  }
}

async function load() {
  const { settings = {}, state = {} } = await chrome.storage.local.get(["settings", "state"]);
  // O que foi salvo nas Opções vale mais que o arquivo do setup.
  return { settings: settings.token ? settings : { ...(await localConfig()), ...settings }, state };
}

async function patchState(patch) {
  const { state } = await load();
  const next = { ...state, ...patch };
  await chrome.storage.local.set({ state: next });
  await refreshBadge(next);
  return next;
}

async function backend() {
  const { settings } = await load();
  if (!settings.token) throw new Error("Configure o token nas opções da extensão.");
  return new Backend(settings.backendUrl || DEFAULT_BACKEND, settings.token);
}

async function refreshBadge(state) {
  const [text, color] = state.paused
    ? ["II", "#D7142B"]
    : state.lastError
      ? ["!", "#E8A100"]
      : ["", "#000000"];
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color });
}

// Coleta e links dividem a aba chamada a chamada (intercalam), com 3 s entre chamadas.
const tabGate = new TabGate(MIN_GAP_BETWEEN_CALLS_MS);
let collecting = false;
let linking = false;

// --- aba do portal -----------------------------------------------------------

function waitComplete(tabId, timeoutMs = 30_000) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      chrome.tabs.onUpdated.removeListener(listener);
      clearTimeout(timer);
      resolve();
    };
    const listener = (id, info) => {
      if (id === tabId && info.status === "complete") finish();
    };
    chrome.tabs.onUpdated.addListener(listener);
    const timer = setTimeout(finish, timeoutMs);
    chrome.tabs.get(tabId).then((tab) => tab.status === "complete" && finish(), finish);
  });
}

/** Aba fixada do portal, criada só na primeira chamada que precisar dela. */
function portalTab(portalUrl) {
  let tabId = null;
  const id = async () => {
    if (tabId !== null) return tabId;
    const [existing] = await chrome.tabs.query({ url: `${PORTAL_PREFIX}*` });
    const tab = existing ?? await chrome.tabs.create({ url: portalUrl, pinned: true, active: false });
    tabId = tab.id;
    await waitComplete(tabId);
    return tabId;
  };
  return {
    inTab: (kind, url, body) => tabGate.run(async () => {
      const [injection] = await chrome.scripting.executeScript({
        target: { tabId: await id() },
        world: "MAIN",
        func: postInPage,
        args: [url, body, kind === "search", CSRF_WAIT_MS],
      });
      return injection?.result ?? { error: "a aba não respondeu" };
    }),
    reloadTab: () => tabGate.run(async () => {
      const tab = await id();
      await chrome.tabs.reload(tab);
      await new Promise((resolve) => setTimeout(resolve, 1000));
      await waitComplete(tab);
    }),
  };
}

// --- freio -------------------------------------------------------------------

async function brake(api, reason, url) {
  try {
    await api.post("/ext/alert", { reason, url: url ?? null });
  } catch {
    // backend fora do ar: a pausa local vale mesmo assim
  }
  await patchState({ paused: true, pauseReason: reason });
}

// --- ciclos ------------------------------------------------------------------

async function collect({ manual = false } = {}) {
  if (collecting) return;
  collecting = true;
  let next = RETRY_AFTER_ERROR_MS;
  try {
    const api = await backend();
    const cfg = await api.get("/ext/config?purpose=collect"); // avança o rodízio de categorias
    next = nextDelayMs(cfg.collect_every_min, cfg.collect_jitter_min);
    await patchState({ cfg, paused: cfg.paused, pauseReason: cfg.pause_reason, lastError: null });
    const tab = portalTab(cfg.portal_url);
    const out = await runCollection({
      cfg,
      backend: api,
      inTab: tab.inTab,
      reloadTab: tab.reloadTab,
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      now: () => new Date(),
      ignoreWindow: manual,
    });
    if (out.status === "blocked") await brake(api, out.reason, out.url);
    await patchState({ lastCollect: { at: Date.now(), ...out } });
  } catch (error) {
    await patchState({ lastError: String(error.message || error), lastErrorAt: Date.now() });
  } finally {
    collecting = false;
    await chrome.alarms.create("collect", { when: Date.now() + next });
  }
}

function todayKey() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" });
}

async function linkStep() {
  if (linking) return;
  linking = true;
  try {
    const { state } = await load();
    const api = await backend();
    const cfg = await api.get("/ext/config");
    if (!collecting && shouldCollectNow(cfg, state.lastCollect?.at, Date.now())) {
      collect(); // estoque curto na nuvem: coleta agora, sem esperar o alarme
    }
    const limiter = RateLimiter.fromJSON(state.linkLimiter ?? { stamps: [] });
    limiter.maxPerHour = cfg.max_links_per_hour;
    const tab = portalTab(cfg.portal_url);
    const out = await runLinkStep({
      cfg,
      backend: api,
      inTab: tab.inTab,
      reloadTab: tab.reloadTab,
      limiter,
      nextLinkAt: state.nextLinkAt ?? 0,
      now: () => new Date(),
    });
    const patch = {
      linkLimiter: limiter.toJSON(),
      nextLinkAt: out.nextLinkAt,
      paused: cfg.paused,
      pauseReason: cfg.pause_reason,
    };
    if (out.status === "done") {
      const today = state.linksToday?.date === todayKey()
        ? state.linksToday
        : { date: todayKey(), ok: 0, failed: 0 };
      patch.linksToday = {
        ...today,
        ok: today.ok + (out.ok ? 1 : 0),
        failed: today.failed + (out.ok ? 0 : 1),
      };
    }
    if (out.status === "blocked") await brake(api, out.reason, out.url);
    await patchState(patch);
  } catch (error) {
    await patchState({ lastError: String(error.message || error), lastErrorAt: Date.now() });
  } finally {
    linking = false;
  }
}

async function ensureAlarms() {
  // 30 s é o mínimo do navegador; o ritmo real é dado por link_gap_s e max_links_per_hour.
  await chrome.alarms.create("links", { periodInMinutes: 0.5 });
  if (!(await chrome.alarms.get("collect"))) {
    await chrome.alarms.create("collect", { when: Date.now() + 60_000 });
  }
}

chrome.runtime.onInstalled.addListener(ensureAlarms);
chrome.runtime.onStartup.addListener(ensureAlarms);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "collect") collect();
  if (alarm.name === "links") linkStep();
});

// --- mensagens do popup e das opções -------------------------------------------

async function handle(message) {
  switch (message.type) {
    case "status": {
      const { settings, state } = await load();
      return { configured: Boolean(settings.token), state };
    }
    case "pause": {
      await brake(await backend(), "manual");
      return { paused: true };
    }
    case "resume": {
      await (await backend()).post("/ext/resume");
      await patchState({ paused: false, pauseReason: null });
      await chrome.alarms.create("collect", { when: Date.now() + 5_000 });
      return { paused: false };
    }
    case "stock": {
      // Estoque na nuvem + o que a extensão está fazendo agora, para o popup.
      const { state } = await load();
      const stock = await (await backend()).get("/ext/stock");
      return { stock, collecting, linking, paused: Boolean(state.paused) };
    }
    case "collectNow": {
      collect({ manual: true });
      return { started: true };
    }
    case "testBackend": {
      return await (await backend()).get("/health");
    }
    default:
      return { error: `mensagem desconhecida: ${message.type}` };
  }
}

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  handle(message).then(reply, (error) => reply({ error: String(error.message || error) }));
  return true; // resposta assíncrona
});
