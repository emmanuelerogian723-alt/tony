/**
 * Tony JS SDK — zero dependencies, works in Node 18+ and the browser.
 *
 *   import { Tony } from "./tony.mjs";
 *   const tony = new Tony("https://tony.example.com", process.env.TONY_KEY);
 *   const out = await tony.execute("github.list_repos", { entityId: "user_42", args: { per_page: 5 } });
 */

export class TonyError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message);
    this.name = "TonyError";
    this.status = status;
    this.detail = detail;
  }
}

export class Tony {
  constructor(baseUrl, apiKey = "", { fetchImpl = globalThis.fetch, timeoutMs = 40000 } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
    this.fetch = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async #request(path, { method = "GET", body, query } = {}) {
    const url = new URL(this.baseUrl + path);
    for (const [k, v] of Object.entries(query || {})) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await this.fetch(url, {
        method,
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          ...(body ? { "Content-Type": "application/json" } : {}),
          ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      const text = await res.text();
      const json = text ? JSON.parse(text) : {};
      if (!res.ok) throw new TonyError(json.detail || `HTTP ${res.status}`, res.status, json);
      return json;
    } finally {
      clearTimeout(timer);
    }
  }

  // catalogue
  async apps({ search = "", category = "" } = {}) {
    return (await this.#request("/v1/apps", { query: { search, category } })).apps || [];
  }

  async app(slug) {
    return this.#request(`/v1/apps/${encodeURIComponent(slug)}`);
  }

  async actions({ search = "", app = "" } = {}) {
    return (await this.#request("/v1/actions", { query: { search, app } })).actions || [];
  }

  async tools(format = "openai") {
    return (await this.#request("/v1/tools", { query: { format } })).tools || [];
  }

  // connections
  async connectUrl(app, entityId, redirectAfter = "/app") {
    const out = await this.#request(`/v1/connections/${encodeURIComponent(app)}/start`, {
      method: "POST",
      body: { entity_id: entityId, redirect_after: redirectAfter },
    });
    return out.authorization_url;
  }

  async connections(entityId) {
    return (await this.#request("/v1/connections", { query: { entity_id: entityId } })).connections || [];
  }

  async disconnect(app, entityId) {
    await this.#request(`/v1/connections/${encodeURIComponent(app)}`, {
      method: "DELETE",
      query: { entity_id: entityId },
    });
  }

  // execution
  async execute(action, { entityId = "default", args = {}, approved = false, dryRun = false } = {}) {
    const out = await this.#request("/v1/execute", {
      method: "POST",
      body: { action, entity_id: entityId, args, approved, dry_run: dryRun },
    });
    return out;
  }

  async approve(runId) {
    return this.#request(`/v1/runs/${encodeURIComponent(runId)}/approve`, { method: "POST" });
  }

  async runs(limit = 25) {
    return (await this.#request("/v1/runs", { query: { limit } })).runs || [];
  }
}

export default Tony;
