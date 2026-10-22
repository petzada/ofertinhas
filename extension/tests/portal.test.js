import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { Backend, BackendError } from "../lib/backend.js";
import { buildSearchBody, cardCount, randomBetween } from "../lib/portal.js";

describe("buildSearchBody", () => {
  it("monta o corpo igual ao que o portal envia, com filtro de categoria", () => {
    assert.deepEqual(buildSearchBody({ id: "MLB1384", name: "Bebês" }, 18), {
      search: "",
      sort: "relevance",
      filters: [{ id: "category", value: "MLB1384", name: "Bebês" }],
      offset: 18,
    });
  });

  it("sem categoria não filtra", () => {
    assert.deepEqual(buildSearchBody(null, 0).filters, []);
  });

  it("busca por termo vai no campo `search`, sem filtro de categoria", () => {
    assert.deepEqual(buildSearchBody(null, 0, "jogo de cama"), {
      search: "jogo de cama",
      sort: "relevance",
      filters: [],
      offset: 0,
    });
  });
});

describe("cardCount", () => {
  it("conta os cards de uma resposta da busca", () => {
    assert.equal(cardCount({ polycard_client_model: { polycards: [{}, {}] } }), 2);
    assert.equal(cardCount({}), 0);
    assert.equal(cardCount(null), 0);
  });
});

describe("randomBetween", () => {
  it("fica no intervalo", () => {
    assert.equal(randomBetween([5, 15], () => 0), 5);
    assert.equal(randomBetween([5, 15], () => 0.999999), 15);
  });
});

describe("Backend", () => {
  function fakeFetch(responses) {
    const calls = [];
    const impl = async (url, init) => {
      calls.push({ url, init });
      const r = responses.shift();
      return { ok: r.status < 400, status: r.status, json: async () => r.body };
    };
    return { calls, impl };
  }

  it("envia o token e o corpo JSON", async () => {
    const f = fakeFetch([{ status: 200, body: { ok: true } }]);
    const backend = new Backend("http://127.0.0.1:8765/", "tok", f.impl);
    assert.deepEqual(await backend.post("/ext/raw", { a: 1 }), { ok: true });
    assert.equal(f.calls[0].url, "http://127.0.0.1:8765/ext/raw");
    assert.equal(f.calls[0].init.headers["X-Ofertinhas-Token"], "tok");
    assert.equal(f.calls[0].init.body, '{"a":1}');
  });

  it("erro HTTP vira BackendError com status", async () => {
    const f = fakeFetch([{ status: 401, body: { detail: "token inválido" } }]);
    const backend = new Backend("http://127.0.0.1:8765", "x", f.impl);
    await assert.rejects(backend.get("/ext/config"), (e) => e instanceof BackendError && e.status === 401);
  });
});
