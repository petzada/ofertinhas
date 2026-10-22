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
  runtime: { onInstalled: event("installed"), onStartup: event("startup"), onMessage: event("message") },
  tabs: { onUpdated: event("tabUpdated") },
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
    assert.deepEqual(alarms.links, { periodInMinutes: 1 });
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

  it("mensagem desconhecida", async () => {
    assert.match((await message("xyz")).error, /desconhecida/);
  });
});
