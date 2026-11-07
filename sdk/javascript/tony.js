/** Tony JavaScript SDK (ESM + CJS friendly, no dependencies). */
export class TonyError extends Error {
  constructor(status, detail) { super(`${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`); this.status = status; this.detail = detail; }
}

export class Tony {
  constructor(apiKey, baseUrl = "https://tony-7su0.onrender.com", session) {
    this.apiKey = apiKey; this.baseUrl = baseUrl.replace(/\/$/, ""); this.session = session;
  }
  async #call(method, path, body) {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: { authorization: `Bearer ${this.apiKey}`, "content-type": "application/json",
                 ...(this.session ? { "x-tony-session": this.session } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) throw new TonyError(res.status, data.detail ?? data);
    return data;
  }
  execute(action, args = {}, approved = false) { return this.#call("POST", "/v1/execute", { action, args, approved }); }
  batch(calls) { return this.#call("POST", "/v1/batch", { calls }); }
  apps(q = "", limit = 50) { return this.#call("GET", `/v1/apps?q=${encodeURIComponent(q)}&limit=${limit}`); }
  tools(fmt = "openai") { return this.#call("GET", `/v1/tools?fmt=${fmt}`); }
  connections() { return this.#call("GET", "/v1/connections"); }
  connect(app) { return this.#call("POST", `/v1/connections/${app}/start`); }
  sessions() { return this.#call("GET", "/v1/sessions"); }
  createSession(input) { return this.#call("POST", "/v1/sessions", input); }
  customTools() { return this.#call("GET", "/v1/custom-tools"); }
  createCustomTool(input) { return this.#call("POST", "/v1/custom-tools", input); }
  ask(message) { return this.#call("POST", "/v1/assistant", { message }); }
}
export default Tony;
