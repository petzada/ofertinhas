// Roda no mundo da própria página do Mercado Livre (world MAIN), antes dos scripts dela.
// Só observa: anota o token CSRF que a página usa nas próprias chamadas, para que as
// chamadas da extensão saiam iguais às da página. Não altera nenhuma requisição.
(() => {
  const ML_HOST = /(^|\.)mercadoli(vre|bre)\.com(\.br)?$/i;
  const auth = { csrf: null, origin: null, at: null };
  window.__ofertinhasAuth = auth;

  function isMlUrl(url) {
    if (typeof url !== "string") return false;
    const match = /^https?:\/\/([^/?#:]+)/i.exec(url);
    return match ? ML_HOST.test(match[1]) : true; // URL relativa: mesma origem da página
  }

  function remember(name, value) {
    const key = String(name).toLowerCase();
    if (key === "x-csrf-token" && value) {
      auth.csrf = String(value);
      auth.at = Date.now();
    } else if (key === "x-custom-origin" && value) {
      auth.origin = String(value);
    }
  }

  function scanHeaders(headers) {
    if (!headers) return;
    if (Array.isArray(headers)) {
      for (const [k, v] of headers) remember(k, v);
    } else if (typeof headers.forEach === "function") {
      headers.forEach((v, k) => remember(k, v));
    } else {
      for (const k of Object.keys(headers)) remember(k, headers[k]);
    }
  }

  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = typeof input === "string" ? input : input && input.url;
      if (isMlUrl(url)) {
        scanHeaders(init && init.headers);
        if (input && typeof input === "object") scanHeaders(input.headers);
      }
    } catch {
      // observar nunca pode quebrar a página
    }
    return originalFetch.apply(this, arguments);
  };

  const proto = window.XMLHttpRequest.prototype;
  const originalOpen = proto.open;
  const originalSetHeader = proto.setRequestHeader;
  proto.open = function (method, url) {
    this.__ofertinhasUrl = url;
    return originalOpen.apply(this, arguments);
  };
  proto.setRequestHeader = function (name, value) {
    try {
      if (isMlUrl(this.__ofertinhasUrl)) remember(name, value);
    } catch {
      // idem
    }
    return originalSetHeader.apply(this, arguments);
  };

  const HTML_PATTERNS = [
    /<meta[^>]+name=["']csrf-token["'][^>]*content=["']([^"']+)["']/i,
    /["']?csrf[-_]?token["']?\s*[:=]\s*["']([0-9a-f-]{36})["']/i,
  ];

  // Plano B quando a página ainda não fez nenhuma chamada: procura o token no HTML.
  window.__ofertinhasFindCsrf = function () {
    const html = (window.document && window.document.documentElement
      && window.document.documentElement.innerHTML) || "";
    for (const pattern of HTML_PATTERNS) {
      const match = pattern.exec(html);
      if (match) return match[1];
    }
    return null;
  };
})();
