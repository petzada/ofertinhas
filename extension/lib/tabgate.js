// Uma chamada por vez na aba do portal, com intervalo mínimo entre elas. Coleta e links
// pedem a vez por chamada (não por ciclo), então se intercalam nas pausas da coleta.

export class TabGate {
  constructor(minGapMs, now = () => Date.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms))) {
    this.minGapMs = minGapMs;
    this.now = now;
    this.sleep = sleep;
    this.chain = Promise.resolve();
    this.lastEnd = -Infinity;
  }

  run(task) {
    const turn = this.chain.then(async () => {
      const wait = this.lastEnd + this.minGapMs - this.now();
      if (wait > 0) await this.sleep(wait);
      try {
        return await task();
      } finally {
        this.lastEnd = this.now();
      }
    });
    this.chain = turn.catch(() => {});
    return turn;
  }
}
