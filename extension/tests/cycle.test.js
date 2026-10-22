import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { runCollection, runLinkStep } from "../lib/cycle.js";
import { RateLimiter } from "../lib/ratelimit.js";

const NOON = new Date("2026-10-22T15:00:00Z"); // 12:00 em São Paulo
const NIGHT = new Date("2026-10-23T03:00:00Z"); // 00:00 em São Paulo

function config(overrides = {}) {
  return {
    paused: false,
    window: ["08:00", "23:00"],
    pages_per_category: 2,
    page_size: 18,
    request_gap_s: [5, 15],
    link_gap_s: [30, 90],
    max_links_per_hour: 30,
    search_url: "https://www.mercadolivre.com.br/affiliate-program/api/hub/search?is_affiliate=true&device=desktop",
    categories: [{ id: "MLB1574", name: "Casa" }, { id: "MLB1648", name: "Informática" }],
    ...overrides,
  };
}

function page(n) {
  return { polycard_client_model: { polycards: Array.from({ length: n }, () => ({})) } };
}

function fakeBackend(replies = {}) {
  const posts = [];
  return {
    posts,
    get: async (path) => replies[path],
    post: async (path, body) => {
      posts.push({ path, body });
      return replies[path] ?? { parsed: 18, new: 3 };
    },
  };
}

function deps(overrides = {}) {
  const sleeps = [];
  return {
    sleeps,
    now: () => NOON,
    sleep: async (ms) => sleeps.push(ms),
    rng: () => 0.5,
    reloadTab: async () => {},
    ...overrides,
  };
}

describe("runCollection", () => {
  it("percorre categorias e páginas, com pausa entre chamadas", async () => {
    const calls = [];
    const backend = fakeBackend();
    const d = deps({
      inTab: async (kind, url, body) => {
        calls.push(body);
        return { status: 200, json: page(18) };
      },
    });
    const out = await runCollection({ cfg: config(), backend, ...d });
    assert.equal(out.status, "ok");
    assert.deepEqual(calls.map((b) => [b.filters[0].value, b.offset]),
      [["MLB1574", 0], ["MLB1574", 18], ["MLB1648", 0], ["MLB1648", 18]]);
    assert.equal(backend.posts.length, 4);
    assert.equal(backend.posts[0].path, "/ext/raw");
    assert.deepEqual(backend.posts[0].body.request_body, calls[0]);
    assert.deepEqual(d.sleeps, [10000, 10000, 10000]);
    assert.equal(out.offers, 72);
    assert.equal(out.newOffers, 12);
  });

  it("página incompleta encerra a categoria", async () => {
    const calls = [];
    const d = deps({
      inTab: async (kind, url, body) => {
        calls.push(body);
        return { status: 200, json: page(body.filters[0].value === "MLB1574" ? 5 : 18) };
      },
    });
    await runCollection({ cfg: config(), backend: fakeBackend(), ...d });
    assert.equal(calls.length, 3);
  });

  it("não faz nada pausada ou fora da janela", async () => {
    const inTab = async () => assert.fail("não deveria chamar o portal");
    assert.equal((await runCollection({ cfg: config({ paused: true }), backend: fakeBackend(),
      ...deps({ inTab }) })).status, "paused");
    assert.equal((await runCollection({ cfg: config(), backend: fakeBackend(),
      ...deps({ inTab, now: () => NIGHT }) })).status, "outside");
  });

  it("403 recarrega a aba uma vez e segue se resolver", async () => {
    let reloads = 0;
    const statuses = [403, 200, 200, 200, 200];
    const d = deps({
      reloadTab: async () => { reloads++; },
      inTab: async () => ({ status: statuses.shift(), json: page(18) }),
    });
    const out = await runCollection({ cfg: config(), backend: fakeBackend(), ...d });
    assert.equal(out.status, "ok");
    assert.equal(reloads, 1);
  });

  it("bloqueio persistente aciona o freio sem enviar nada", async () => {
    const backend = fakeBackend();
    const d = deps({ inTab: async () => ({ status: 403, json: null }) });
    const out = await runCollection({ cfg: config(), backend, ...d });
    assert.equal(out.status, "blocked");
    assert.equal(out.reason, "http");
    assert.equal(backend.posts.length, 0);
  });

  it("tela de login ou captcha aciona o freio na hora", async () => {
    const login = deps({ inTab: async () => ({ status: 200, location: "https://www.mercadolivre.com.br/login/identification?x=1" }) });
    assert.equal((await runCollection({ cfg: config(), backend: fakeBackend(), ...login })).reason, "login");
    const captcha = deps({ inTab: async () => ({ status: 200, captcha: true }) });
    assert.equal((await runCollection({ cfg: config(), backend: fakeBackend(), ...captcha })).reason, "captcha");
  });

  it("sem token CSRF recarrega uma vez e depois freia", async () => {
    let reloads = 0;
    const d = deps({ reloadTab: async () => { reloads++; }, inTab: async () => ({ error: "no-csrf" }) });
    const out = await runCollection({ cfg: config(), backend: fakeBackend(), ...d });
    assert.equal(out.status, "blocked");
    assert.equal(out.reason, "csrf");
    assert.equal(reloads, 1);
  });
});

describe("runLinkStep", () => {
  const request = { mlb_id: "MLB1", url: "https://www.mercadolivre.com.br/x/createLink", body: { itemId: "MLB1" } };

  function linkDeps(overrides = {}) {
    return {
      cfg: config(),
      limiter: new RateLimiter(30, () => NOON.getTime()),
      nextLinkAt: 0,
      now: () => NOON,
      rng: () => 0,
      ...overrides,
    };
  }

  it("gera o link e devolve a resposta ao backend", async () => {
    const backend = fakeBackend({ "/ext/link-requests": { request }, "/ext/links": { ok: true } });
    const inTab = async (kind, url, body) => {
      assert.equal(kind, "createLink");
      assert.deepEqual(body, request.body);
      return { status: 200, json: { total_error: 0 } };
    };
    const d = linkDeps();
    const out = await runLinkStep({ backend, inTab, ...d });
    assert.equal(out.status, "done");
    assert.equal(out.ok, true);
    assert.deepEqual(backend.posts[0], { path: "/ext/links", body: { mlb_id: "MLB1", response: { total_error: 0 } } });
    assert.equal(out.nextLinkAt, NOON.getTime() + 30_000);
    assert.equal(d.limiter.canProceed(), true);
    assert.equal(d.limiter.stamps.length, 1);
  });

  it("erro HTTP comum é reportado como falha do link", async () => {
    const backend = fakeBackend({ "/ext/link-requests": { request }, "/ext/links": { ok: false } });
    const out = await runLinkStep({ backend, inTab: async () => ({ status: 500 }), ...linkDeps() });
    assert.equal(out.status, "done");
    assert.deepEqual(backend.posts[0].body, { mlb_id: "MLB1", error: "HTTP 500" });
  });

  it("bloqueio não conta como falha do link: freia", async () => {
    const backend = fakeBackend({ "/ext/link-requests": { request } });
    const out = await runLinkStep({ backend, inTab: async () => ({ status: 429 }), ...linkDeps() });
    assert.equal(out.status, "blocked");
    assert.equal(backend.posts.length, 0);
  });

  it("respeita o intervalo, o limite por hora e a fila vazia", async () => {
    const inTab = async () => assert.fail("não deveria gerar link");
    const empty = fakeBackend({ "/ext/link-requests": { request: null } });
    assert.equal((await runLinkStep({ backend: empty, inTab, ...linkDeps({ nextLinkAt: NOON.getTime() + 1 }) })).status, "wait");
    const full = new RateLimiter(0, () => NOON.getTime());
    assert.equal((await runLinkStep({ backend: empty, inTab, ...linkDeps({ limiter: full }) })).status, "limit");
    assert.equal((await runLinkStep({ backend: empty, inTab, ...linkDeps() })).status, "idle");
  });
});
