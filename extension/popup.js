import { withinWindow } from "./lib/schedule.js";
import { describeStock } from "./lib/stock.js";

const $ = (id) => document.getElementById(id);
const REASONS = {
  login: "sessão do ML expirou (faça login no Brave)",
  captcha: "o ML pediu verificação (resolva no Brave)",
  http: "o ML recusou as chamadas",
  csrf: "não achei o token da página",
  manual: "pausada por você",
};

function send(type) {
  return chrome.runtime.sendMessage({ type });
}

function time(ms) {
  return new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function describeCollect(last) {
  if (!last) return "ainda não houve";
  const at = time(last.at);
  switch (last.status) {
    case "outside": return `${at} · fora do horário, nada coletado`;
    case "paused": return `${at} · pausada, nada coletado`;
    case "blocked": return `${at} · parou: ${REASONS[last.reason] || last.reason}`;
    default: return `${at} · ${last.offers ?? 0} ofertas (${last.newOffers ?? 0} novas)`;
  }
}

async function render() {
  const { configured, state = {}, error } = await send("status");
  const status = $("status");
  $("error").hidden = true;
  if (error || !configured) {
    status.textContent = "Falta configurar o token";
    status.className = "status bad";
    $("error").textContent = error || "Abra as Opções e cole o token do backend.";
    $("error").hidden = false;
    return;
  }
  if (state.paused) {
    status.textContent = `Pausada: ${REASONS[state.pauseReason] || state.pauseReason || "motivo desconhecido"}`;
    status.className = "status bad";
  } else if (state.cfg && !withinWindow(new Date(), state.cfg.window)) {
    status.textContent = `Fora do horário (${state.cfg.window.join("–")})`;
    status.className = "status warn";
  } else {
    status.textContent = "Ativa";
    status.className = "status ok";
  }
  if (state.lastError) {
    $("error").textContent = `Último erro (${time(state.lastErrorAt)}): ${state.lastError}`;
    $("error").hidden = false;
  }
  $("last-collect").textContent = describeCollect(state.lastCollect);
  const today = state.linksToday;
  $("links-today").textContent = today && today.date === new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" })
    ? `${today.ok} gerados${today.failed ? ` · ${today.failed} falharam` : ""}`
    : "0";
  const toggle = $("toggle");
  toggle.textContent = state.paused ? "Retomar" : "Pausar";
  toggle.disabled = false;
  $("collect").disabled = Boolean(state.paused);
}

async function renderStock() {
  const reply = await send("stock");
  if (!reply || reply.error) {
    $("stock-note").textContent = reply?.error ? `Estoque indisponível: ${reply.error}` : "";
    $("stock-note").className = "status bad";
    return;
  }
  const text = describeStock(reply.stock, reply);
  $("stock-ready").textContent = text.ready;
  $("stock-waiting").textContent = text.waiting;
  $("stock-until").textContent = text.until;
  $("stock-note").textContent = text.note;
  $("stock-note").className = `status ${text.tone}`;
}

$("toggle").addEventListener("click", async () => {
  const { state = {} } = await send("status");
  const result = await send(state.paused ? "resume" : "pause");
  if (result?.error) {
    $("error").textContent = result.error;
    $("error").hidden = false;
  }
  await render();
renderStock();
setInterval(renderStock, 5_000); // acompanha os links enquanto o popup está aberto
});

$("collect").addEventListener("click", async () => {
  $("collect").disabled = true;
  $("collect").textContent = "Coletando…";
  await send("collectNow");
  setTimeout(() => {
    $("collect").textContent = "Coletar agora";
    render();
renderStock();
setInterval(renderStock, 5_000); // acompanha os links enquanto o popup está aberto
  }, 1500);
});

render();
renderStock();
setInterval(renderStock, 5_000); // acompanha os links enquanto o popup está aberto
