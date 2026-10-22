import { withinWindow } from "./lib/schedule.js";

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
  const last = state.lastCollect;
  $("last-collect").textContent = last
    ? `${time(last.at)} · ${last.offers ?? 0} ofertas (${last.newOffers ?? 0} novas)`
    : "ainda não houve";
  const today = state.linksToday;
  $("links-today").textContent = today && today.date === new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" })
    ? `${today.ok} gerados${today.failed ? ` · ${today.failed} falharam` : ""}`
    : "0";
  const toggle = $("toggle");
  toggle.textContent = state.paused ? "Retomar" : "Pausar";
  toggle.disabled = false;
  $("collect").disabled = Boolean(state.paused);
}

$("toggle").addEventListener("click", async () => {
  const { state = {} } = await send("status");
  const result = await send(state.paused ? "resume" : "pause");
  if (result?.error) {
    $("error").textContent = result.error;
    $("error").hidden = false;
  }
  await render();
});

$("collect").addEventListener("click", async () => {
  $("collect").disabled = true;
  $("collect").textContent = "Coletando…";
  await send("collectNow");
  setTimeout(() => {
    $("collect").textContent = "Coletar agora";
    render();
  }, 1500);
});

render();
