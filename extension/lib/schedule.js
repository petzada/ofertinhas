// Janela de horário (São Paulo) e intervalos com variação aleatória.

const spClock = new Intl.DateTimeFormat("en-GB", {
  timeZone: "America/Sao_Paulo",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function minutesOf(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/** `window` é ["HH:MM", "HH:MM"]; início inclusivo, fim exclusivo. */
export function withinWindow(date, window) {
  const now = minutesOf(spClock.format(date));
  return now >= minutesOf(window[0]) && now < minutesOf(window[1]);
}

/** Intervalo em ms: base ± variação (minutos), nunca menor que 1 minuto. */
export function nextDelayMs(baseMin, jitterMin, rng = Math.random) {
  const minutes = baseMin + (rng() * 2 - 1) * jitterMin;
  return Math.max(1, minutes) * 60_000;
}
