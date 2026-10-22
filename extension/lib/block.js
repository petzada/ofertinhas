// Sinais de que o Mercado Livre bloqueou ou deslogou a sessão. Qualquer um aciona o freio.

const ML_HOSTS = ["mercadolivre.com", "mercadolibre.com"];
const CAPTCHA_MARKERS = ["g-recaptcha", "h-captcha", "hcaptcha", "recaptcha/api", "captcha-container"];
const BLOCK_STATUS = new Set([401, 403, 429]);

function isMlUrl(url) {
  try {
    const host = new URL(url).hostname;
    return ML_HOSTS.some((h) => host.includes(h));
  } catch {
    return false;
  }
}

/** Devolve "login", "captcha", "http" ou null. */
export function detectBlock({ url, status, html }) {
  if (isMlUrl(url)) {
    const path = new URL(url).pathname.toLowerCase();
    if (path.split("/").includes("login") || path.includes("no-feasible-authenticators")) {
      return "login";
    }
  }
  if (html && CAPTCHA_MARKERS.some((m) => html.includes(m))) {
    return "captcha";
  }
  if (BLOCK_STATUS.has(status)) {
    return "http";
  }
  return null;
}
