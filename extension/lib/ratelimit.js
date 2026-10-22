// Limite de ações por hora em janela deslizante. Serializável, porque o service worker
// do MV3 é encerrado e reiniciado pelo navegador a qualquer momento.

const HOUR_MS = 60 * 60_000;

export class RateLimiter {
  constructor(maxPerHour, now = () => Date.now(), stamps = []) {
    this.maxPerHour = maxPerHour;
    this.now = now;
    this.stamps = stamps;
  }

  #prune() {
    const cutoff = this.now() - HOUR_MS;
    this.stamps = this.stamps.filter((t) => t > cutoff);
  }

  canProceed() {
    this.#prune();
    return this.stamps.length < this.maxPerHour;
  }

  record() {
    this.stamps.push(this.now());
  }

  toJSON() {
    return { maxPerHour: this.maxPerHour, stamps: this.stamps };
  }

  static fromJSON(data, now = () => Date.now()) {
    return new RateLimiter(data.maxPerHour, now, data.stamps ?? []);
  }
}
