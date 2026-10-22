import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";

describe("popup.js", () => {
  it("tem um só timer de estoque, de 20 s (cada consulta roda na nuvem)", async () => {
    const source = await readFile(new URL("../popup.js", import.meta.url), "utf-8");
    const timers = [...source.matchAll(/setInterval\(renderStock, ([\d_]+)\)/g)];
    assert.equal(timers.length, 1);
    assert.equal(Number(timers[0][1].replaceAll("_", "")), 20_000);
  });
});
