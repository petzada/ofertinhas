// Cliente da API local do backend (127.0.0.1), autenticado pelo token do .env.

export class BackendError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export class Backend {
  constructor(baseUrl, token, fetchImpl = (...args) => fetch(...args)) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.token = token;
    this.fetchImpl = fetchImpl;
  }

  async request(method, path, body) {
    const response = await this.fetchImpl(this.baseUrl + path, {
      method,
      headers: { "X-Ofertinhas-Token": this.token, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try {
      data = await response.json();
    } catch {
      // resposta sem JSON
    }
    if (!response.ok) {
      throw new BackendError(response.status, data?.detail || `HTTP ${response.status}`);
    }
    return data;
  }

  get(path) {
    return this.request("GET", path);
  }

  post(path, body = {}) {
    return this.request("POST", path, body);
  }
}
