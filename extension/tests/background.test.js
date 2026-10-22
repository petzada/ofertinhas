// Carrega o service worker com um `chrome` falso: confere que os imports resolvem, que os
// eventos são registrados e que o popup recebe o estado.
import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

const listeners = {};
const storage = {};
const alarms = {};

function event(name) {
  return { addListener: (fn) => { listeners[name] = fn; }, removeListener() {} };
}

globalThis.chrome = {
  storage: {
    local: {
      get: async (keys) => Object.fromEntries([keys].flat().filter((k) => k in storage).map((k) => [k, storage[k]])),
      set: async (items) => Object.assign(storage, items),
    },
  },
  action: { setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {} },
  alarms: {
    create: async (name, info) => { alarms[name] = info; },
    get: async (name) => alarms[name],
    onAlarm: event("alarm"),
  },
  runtime: {
    onInstalled: event("installed"),
    onStartup: event("startup"),
    onMessage: event("message"),
    getURL: (path) => `chrome-extension://teste/${path}`,
  },
  tabs: { onUpdated: event("tabUpdated") },
};

// config.local.json (gerado por `python -m ofertinhas setup`): ausente até o teste criar
let localConfig = null;
globalThis.fetch = async (url) => {
  if (url === "chrome-extension://teste/config.local.json" && localConfig) {
    return { ok: true, json: async () => localConfig };
  }
  return { ok: false, json: async () => ({}) };
};

function message(type) {
  return new Promise((resolve) => {
    const keepOpen = listeners.message({ type }, {}, resolve);
    assert.equal(keepOpen, true);
  });
}

describe("background.js", () => {
  before(async () => {
    await import("../background.js");
  });

  it("registra instalação, inicialização, alarmes e mensagens", () => {
    for (const name of ["installed", "startup", "alarm", "message"]) {
      assert.equal(typeof listeners[name], "function", name);
    }
  });

  it("cria os alarmes ao instalar", async () => {
    await listeners.installed();
    assert.deepEqual(alarms.links, { periodInMinutes: 0.5 });
    assert.ok(alarms.collect.when > Date.now());
  });

  it("popup sem token configurado", async () => {
    const reply = await message("status");
    assert.equal(reply.configured, false);
  });

  it("ações que precisam do backend explicam a falta do token", async () => {
    const reply = await message("pause");
    assert.match(reply.error, /token/);
  });

  it("usa o config.local.json gerado pelo setup quando não há opções salvas", async () => {
    localConfig = { backendUrl: "http://127.0.0.1:8765", token: "tok-do-setup" };
    const reply = await message("status");
    assert.equal(reply.configured, true);
    localConfig = null;
  });

  it("opções salvas têm prioridade sobre o config.local.json", async () => {
    storage.settings = { backendUrl: "http://127.0.0.1:9000", token: "tok-das-opcoes" };
    localConfig = { backendUrl: "http://127.0.0.1:8765", token: "outro" };
    const reply = await message("status");
    assert.equal(reply.configured, true);
    delete storage.settings;
    localConfig = null;
  });

  it("estoque vem do backend junto com o estado da extensão", async () => {
    localConfig = { backendUrl: "https://nuvem.example", token: "tok" };
    const realFetch = globalThis.fetch;
    const calls = [];
    globalThis.fetch = async (url, init) => {
      if (url.startsWith("https://nuvem.example")) {
        calls.push([url, init.headers["X-Ofertinhas-Token"]]);
        return { ok: true, json: async () => ({ ready: 2, waiting_links: 5, groups: [] }) };
      }
      return realFetch(url, init);
    };
    const reply = await message("stock");
    assert.deepEqual(calls, [["https://nuvem.example/ext/stock", "tok"]]);
    assert.equal(reply.stock.waiting_links, 5);
    assert.equal(reply.collecting, false);
    globalThis.fetch = realFetch;
    localConfig = null;
  });

  it("mensagem desconhecida", async () => {
    assert.match((await message("xyz")).error, /desconhecida/);
  });
});
