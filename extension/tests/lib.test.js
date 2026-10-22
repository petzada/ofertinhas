import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { detectBlock } from "../lib/block.js";
import { matchesCapture } from "../lib/patterns.js";
import { RateLimiter } from "../lib/ratelimit.js";
import { nextDelayMs, shouldCollectNow, withinWindow } from "../lib/schedule.js";

describe("matchesCapture", () => {
  const patterns = ["https://www.mercadolivre.com.br/affiliate*/api/*", "*://api.mercadolibre.com/x"];

  it("aceita URL que casa com curinga", () => {
    assert.equal(matchesCapture("https://www.mercadolivre.com.br/affiliate-program/api/offers?p=1", patterns), true);
    assert.equal(matchesCapture("https://api.mercadolibre.com/x", patterns), true);
  });

  it("recusa URL fora dos padrões", () => {
    assert.equal(matchesCapture("https://www.mercadolivre.com.br/afiliados", patterns), false);
    assert.equal(matchesCapture("https://api.mercadolibre.com/xy", patterns), false);
  });

  it("trata caracteres especiais do padrão como literais", () => {
    assert.equal(matchesCapture("https://a.com/x?y=1", ["https://a.com/x?y=1"]), true);
    assert.equal(matchesCapture("https://a.com/xzy=1", ["https://a.com/x?y=1"]), false);
  });
});

describe("withinWindow (horário de São Paulo)", () => {
  const win = ["08:00", "23:00"];

  it("início é inclusivo e fim é exclusivo", () => {
    assert.equal(withinWindow(new Date("2026-10-22T10:59:00Z"), win), false); // 07:59
    assert.equal(withinWindow(new Date("2026-10-22T11:00:00Z"), win), true); // 08:00
    assert.equal(withinWindow(new Date("2026-10-23T01:59:00Z"), win), true); // 22:59
    assert.equal(withinWindow(new Date("2026-10-23T02:00:00Z"), win), false); // 23:00
  });
});

describe("withinWindow sem janela", () => {
  it("janela nula vale a qualquer hora", () => {
    assert.equal(withinWindow(new Date("2026-10-22T05:00:00Z"), null), true);
  });
});

describe("nextDelayMs", () => {
  it("fica dentro de base ± variação", () => {
    for (const r of [0, 0.25, 0.5, 0.999]) {
      const ms = nextDelayMs(20, 5, () => r);
      assert.ok(ms >= 15 * 60_000 && ms <= 25 * 60_000, String(ms));
    }
  });

  it("nunca é menor que 1 minuto", () => {
    assert.equal(nextDelayMs(1, 5, () => 0), 60_000);
  });
});

describe("detectBlock", () => {
  it("detecta tela de login do ML", () => {
    assert.equal(detectBlock({ url: "https://www.mercadolivre.com.br/login/identification?x=1" }), "login");
    assert.equal(detectBlock({ url: "https://www.mercadolivre.com/jms/mlb/lgz/login" }), "login");
    assert.equal(
      detectBlock({ url: "https://www.mercadolivre.com.br/x/no-feasible-authenticators?c=1" }),
      "login",
    );
  });

  it("não confunde produto com 'login' no nome", () => {
    assert.equal(detectBlock({ url: "https://produto.mercadolivre.com.br/MLB-1-mouse-login-gamer" }), null);
  });

  it("detecta captcha no HTML", () => {
    const html = '<div class="g-recaptcha" data-sitekey="x"></div>';
    assert.equal(detectBlock({ url: "https://www.mercadolivre.com.br/afiliados", html }), "captcha");
  });

  it("detecta status de bloqueio", () => {
    for (const status of [401, 403, 429]) {
      assert.equal(detectBlock({ url: "https://www.mercadolivre.com.br/api/x", status }), "http");
    }
    assert.equal(detectBlock({ url: "https://www.mercadolivre.com.br/api/x", status: 200 }), null);
  });
});

describe("RateLimiter", () => {
  it("bloqueia acima do limite na última hora e libera depois", () => {
    let now = 0;
    const rl = new RateLimiter(2, () => now);
    assert.equal(rl.canProceed(), true);
    rl.record();
    rl.record();
    assert.equal(rl.canProceed(), false);
    now = 60 * 60_000 + 1;
    assert.equal(rl.canProceed(), true);
  });

  it("sobrevive a serialização (service worker reinicia)", () => {
    const now = 1000;
    const rl = new RateLimiter(1, () => now);
    rl.record();
    const restored = RateLimiter.fromJSON(JSON.parse(JSON.stringify(rl)), () => now);
    assert.equal(restored.canProceed(), false);
  });
});

describe("shouldCollectNow", () => {
  const now = Date.parse("2026-10-22T15:00:00Z");
  const cfg = { collect_now: true, collect_now_gap_min: 30 };

  it("coleta quando a nuvem pede e nunca coletou", () => {
    assert.equal(shouldCollectNow(cfg, undefined, now), true);
  });

  it("respeita o intervalo mínimo desde a última coleta", () => {
    assert.equal(shouldCollectNow(cfg, now - 29 * 60_000, now), false);
    assert.equal(shouldCollectNow(cfg, now - 30 * 60_000, now), true);
  });

  it("não coleta sem pedido da nuvem", () => {
    assert.equal(shouldCollectNow({ collect_now: false }, undefined, now), false);
    assert.equal(shouldCollectNow(null, undefined, now), false);
  });
});
