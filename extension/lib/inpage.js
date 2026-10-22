// Função executada DENTRO da aba do portal (chrome.scripting.executeScript, world MAIN).
// Precisa ser autocontida: o navegador serializa o código, então nada de imports ou
// referências a funções de fora. Usa o token que content-main.js anotou.

export async function postInPage(url, body, includeOrigin, waitMs) {
  const started = Date.now();
  const findCsrf = () => {
    const auth = window.__ofertinhasAuth || {};
    return auth.csrf || (window.__ofertinhasFindCsrf ? window.__ofertinhasFindCsrf() : null);
  };
  const isChallenge = () =>
    Boolean(document.querySelector(".g-recaptcha"))
    || /Por segurança, complete esta etapa/i.test(document.body ? document.body.innerText : "");

  let csrf = findCsrf();
  while (!csrf && Date.now() - started < waitMs) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    csrf = findCsrf();
  }
  if (isChallenge()) return { captcha: true, location: location.href };
  if (!csrf) return { error: "no-csrf", location: location.href };

  const headers = {
    accept: "application/json, text/plain, */*",
    "content-type": "application/json",
    "x-csrf-token": csrf,
  };
  if (includeOrigin) {
    headers["x-custom-origin"] = (window.__ofertinhasAuth || {}).origin || location.origin;
  }
  try {
    const response = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify(body),
    });
    let json = null;
    try {
      json = await response.json();
    } catch {
      // corpo vazio ou não-JSON
    }
    return { status: response.status, json, location: location.href };
  } catch (error) {
    return { error: String(error), location: location.href };
  }
}
