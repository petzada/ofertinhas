const $ = (id) => document.getElementById(id);

async function loadSettings() {
  const { settings = {} } = await chrome.storage.local.get("settings");
  $("backend").value = settings.backendUrl || "http://127.0.0.1:8765";
  $("token").value = settings.token || "";
}

async function save() {
  const settings = { backendUrl: $("backend").value.trim(), token: $("token").value.trim() };
  await chrome.storage.local.set({ settings });
  $("result").textContent = "Salvo.";
}

$("save").addEventListener("click", save);

$("test").addEventListener("click", async () => {
  await save();
  $("result").textContent = "Testando…";
  const result = await chrome.runtime.sendMessage({ type: "testBackend" });
  $("result").textContent = result?.ok
    ? `Conectado ao backend (versão ${result.version}).`
    : `Falhou: ${result?.error || "sem resposta"}. O backend está rodando?`;
});

loadSettings();
