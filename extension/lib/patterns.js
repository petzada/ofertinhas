// Padrões de URL com curinga `*`, definidos pelo backend em /ext/config.

const cache = new Map();

function toRegExp(pattern) {
  if (!cache.has(pattern)) {
    const escaped = pattern.split("*").map((part) => part.replace(/[.+?^${}()|[\]\\]/g, "\\$&"));
    cache.set(pattern, new RegExp(`^${escaped.join(".*")}$`));
  }
  return cache.get(pattern);
}

export function matchesCapture(url, patterns) {
  return patterns.some((p) => toRegExp(p).test(url));
}
