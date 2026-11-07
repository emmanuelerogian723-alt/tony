/**
 * Tony TypeScript SDK. No runtime dependencies, works in Node 18+, Bun, Deno
 * and edge runtimes that expose fetch.
 *
 *   const tony = new Tony(process.env.TONY_KEY!);
 *   await tony.execute("github.list_repos", { per_page: 3 });
 */
export type Json = Record<string, unknown>;

export class TonyError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`${status}: ${JSON.stringify(detail)}`);
  }
}

export class Tony {
  constructor(
    private apiKey: string,
    private baseUrl = "https://tony-7su0.onrender.com",
    private session?: string,
  ) {}

  private async call<T = Json>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(this.baseUrl.replace(/\/$/, "") + path, {
      method,
      headers: {
        authorization: `Bearer ${this.apiKey}`,
        "content-type": "application/json",
        ...(this.session ? { "x-tony-session": this.session } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) throw new TonyError(res.status, (data as Json).detail ?? data);
    return data as T;
  }

  execute(action: string, args: Json = {}, approved = false) {
    return this.call("POST", "/v1/execute", { action, args, approved });
  }
  batch(calls: { action: string; args?: Json }[]) {
    if (calls.length > 20) throw new Error("Tony accepts at most 20 calls per batch");
    return this.call("POST", "/v1/batch", { calls });
  }
  apps(q = "", limit = 50) {
    return this.call("GET", `/v1/apps?q=${encodeURIComponent(q)}&limit=${limit}`);
  }
  tools(fmt: "openai" | "anthropic" = "openai") {
    return this.call("GET", `/v1/tools?fmt=${fmt}`);
  }
  connections() {
    return this.call("GET", "/v1/connections");
  }
  connect(app: string) {
    return this.call("POST", `/v1/connections/${app}/start`);
  }
  sessions() {
    return this.call("GET", "/v1/sessions");
  }
  createSession(input: { entity_id: string; apps?: string[]; tiers?: string[]; ttl_hours?: number }) {
    return this.call("POST", "/v1/sessions", input);
  }
  customTools() {
    return this.call("GET", "/v1/custom-tools");
  }
  createCustomTool(input: { slug: string; url: string; method?: string; tier?: string; secret?: string }) {
    return this.call("POST", "/v1/custom-tools", input);
  }
  rate(app: string, stars: number, review = "") {
    return this.call("POST", "/v1/ratings", { app_slug: app, stars, review });
  }
  ask(message: string) {
    return this.call("POST", "/v1/assistant", { message });
  }

  /** Vercel AI SDK tool map. */
  async vercelTools() {
    const { tools } = await this.tools();
    const out: Json = {};
    for (const t of tools as { function: { name: string; description: string; parameters: unknown } }[]) {
      out[t.function.name] = {
        description: t.function.description,
        parameters: t.function.parameters,
        execute: (args: Json) => this.execute(t.function.name.replace("__", "."), args),
      };
    }
    return out;
  }
}

export default Tony;
