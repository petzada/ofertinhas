// content-main.js roda no mundo da página (script clássico). Aqui ele é carregado num
// contexto `vm` com window/fetch/XMLHttpRequest falsos.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import vm from "node:vm";

const SOURCE = readFileSync(new URL("../content-main.js", import.meta.url), "utf8");
const CSRF = "0f8c2a5e-1b2c-4d5e-8f90-123456789abc";

function load(html = "<html></html>") {
  const seen = [];
  class FakeXHR {
    open(method, url) { this.url = url; }
    setRequestHeader(name, value) { seen.push([name, value]); }
  }
  const window = {
    location: { origin: "https://www.mercadolivre.com.br" },
    fetch: async (input, init) => ({ input, init }),
    XMLHttpRequest: FakeXHR,
    document: { documentElement: { innerHTML: html } },
  };
  window.window = window;
  vm.createContext(window);
  vm.runInContext(SOURCE, window);
  return { window, seen };
}

describe("content-main.js", () => {
  it("captura o token das chamadas fetch da página e repassa a chamada", async () => {
    const { window } = load();
    const result = await window.fetch("https://www.mercadolivre.com.br/maxwell/api/x", {
      headers: { "X-CSRF-Token": CSRF, "x-custom-origin": "https://www.mercadolivre.com.br" },
    });
    assert.equal(result.init.headers["X-CSRF-Token"], CSRF);
    assert.equal(window.__ofertinhasAuth.csrf, CSRF);
    assert.equal(window.__ofertinhasAuth.origin, "https://www.mercadolivre.com.br");
  });

  it("captura de Headers em formato de lista e de XHR", () => {
    const { window } = load();
    window.fetch("/api/y", { headers: [["x-csrf-token", "a".repeat(36)]] });
    assert.equal(window.__ofertinhasAuth.csrf, "a".repeat(36));
    const xhr = new window.XMLHttpRequest();
    xhr.open("POST", "/api/z");
    xhr.setRequestHeader("x-csrf-token", "b".repeat(36));
    assert.equal(window.__ofertinhasAuth.csrf, "b".repeat(36));
  });

  it("ignora chamadas para outros domínios", () => {
    const { window } = load();
    window.fetch("https://outro.example/api", { headers: { "x-csrf-token": CSRF } });
    assert.equal(window.__ofertinhasAuth.csrf, null);
  });

  it("procura o token no HTML quando a página ainda não fez chamadas", () => {
    const { window } = load(`<script>window.__STATE__ = {"csrfToken":"${CSRF}","x":1}</script>`);
    assert.equal(window.__ofertinhasFindCsrf(), CSRF);
    const meta = load(`<meta name="csrf-token" content="${CSRF}">`);
    assert.equal(meta.window.__ofertinhasFindCsrf(), CSRF);
    assert.equal(load("<p>nada</p>").window.__ofertinhasFindCsrf(), null);
  });
});
