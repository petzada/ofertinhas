import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { describeStock } from "../lib/stock.js";

const at = (hhmm) => `2026-10-22T${hhmm}:00-03:00`;

describe("describeStock", () => {
  it("pede para manter aberto enquanto faltam links", () => {
    const text = describeStock({
      ready: 3, waiting_links: 12,
      groups: [{ ends_at: at("09:15"), ends_at_with_links: at("13:40") }],
    });
    assert.equal(text.ready, "3");
    assert.equal(text.waiting, "12");
    assert.equal(text.until, "até 09:15 (até 13:40 com os links)");
    assert.match(text.note, /faltam 12 \(~12 min\)/);
    assert.equal(text.tone, "warn");
  });

  it("libera fechar quando todos os links saíram", () => {
    const text = describeStock({
      ready: 15, waiting_links: 0, groups: [{ ends_at: at("14:05"), ends_at_with_links: at("14:05") }],
    });
    assert.equal(text.until, "até 14:05");
    assert.match(text.note, /Pode fechar o Brave/);
    assert.equal(text.tone, "ok");
  });

  it("estoque que cobre o dia não tem horário de fim", () => {
    const text = describeStock({ ready: 20, waiting_links: 0, groups: [{ ends_at: null }] });
    assert.equal(text.until, "o resto do dia");
  });

  it("sem nada no estoque, pede para coletar", () => {
    const text = describeStock({ ready: 0, waiting_links: 0, groups: [{ ends_at: at("08:00") }] });
    assert.match(text.note, /Sem estoque/);
    assert.equal(text.tone, "bad");
  });

  it("coleta em andamento e pausa têm prioridade no aviso", () => {
    const stock = { ready: 0, waiting_links: 0, groups: [] };
    assert.match(describeStock(stock, { collecting: true }).note, /Coletando/);
    assert.equal(describeStock(stock, { paused: true }).tone, "bad");
  });
});
