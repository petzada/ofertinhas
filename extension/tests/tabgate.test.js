import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { TabGate } from "../lib/tabgate.js";

function clock() {
  let now = 0;
  const waits = [];
  return {
    waits,
    now: () => now,
    advance: (ms) => { now += ms; },
    sleep: async (ms) => { waits.push(ms); now += ms; },
  };
}

describe("TabGate", () => {
  it("uma chamada por vez, na ordem de chegada", async () => {
    const c = clock();
    const gate = new TabGate(0, c.now, c.sleep);
    const log = [];
    const slow = gate.run(async () => { log.push("a:start"); await c.sleep(10); log.push("a:end"); });
    const fast = gate.run(async () => { log.push("b"); return 42; });
    await slow;
    assert.equal(await fast, 42);
    assert.deepEqual(log, ["a:start", "a:end", "b"]);
  });

  it("espera o intervalo mínimo desde o fim da chamada anterior", async () => {
    const c = clock();
    const gate = new TabGate(3000, c.now, c.sleep);
    await gate.run(async () => {});
    c.advance(1000);
    await gate.run(async () => {});
    assert.deepEqual(c.waits, [2000]);
  });

  it("não espera se o intervalo já passou", async () => {
    const c = clock();
    const gate = new TabGate(3000, c.now, c.sleep);
    await gate.run(async () => {});
    c.advance(5000);
    await gate.run(async () => {});
    assert.deepEqual(c.waits, []);
  });

  it("uma chamada que falha não trava as próximas", async () => {
    const c = clock();
    const gate = new TabGate(0, c.now, c.sleep);
    await assert.rejects(gate.run(async () => { throw new Error("boom"); }));
    assert.equal(await gate.run(async () => "ok"), "ok");
  });
});
