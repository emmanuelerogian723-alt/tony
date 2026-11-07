package dev.tony;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;

/**
 * Tony Java SDK. Java 17+, no dependencies.
 *
 * <pre>
 *   Tony tony = new Tony(System.getenv("TONY_KEY"));
 *   var res = tony.execute("github.list_repos", Map.of("per_page", 3), false);
 * </pre>
 */
public class Tony {
    public static final String DEFAULT_BASE = "https://tony-7su0.onrender.com";

    public record Call(String action, Map<String, Object> args) {}

    public static class TonyException extends RuntimeException {
        public final int status;
        public final String detail;
        public TonyException(int status, String detail) {
            super("Tony " + status + ": " + detail);
            this.status = status;
            this.detail = detail;
        }
    }

    private final String apiKey;
    private final String baseUrl;
    private final String session;
    private final HttpClient http = HttpClient.newHttpClient();
    private final com.fasterxml.jackson.databind.ObjectMapper json =
        new com.fasterxml.jackson.databind.ObjectMapper();

    public Tony(String apiKey) { this(apiKey, DEFAULT_BASE, null); }

    public Tony(String apiKey, String baseUrl, String session) {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.session = session;
    }

    private Map<String, Object> call(String method, String path, Object body) {
        try {
            HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(baseUrl + path))
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .timeout(java.time.Duration.ofSeconds(60));
            if (session != null) b.header("X-Tony-Session", session);
            if (body != null) b.method(method, HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)));
            else b.method(method, HttpRequest.BodyPublishers.noBody());
            HttpResponse<String> res = http.send(b.build(), HttpResponse.BodyHandlers.ofString());
            @SuppressWarnings("unchecked")
            Map<String, Object> out = res.body().isEmpty() ? Map.of() : json.readValue(res.body(), Map.class);
            if (res.statusCode() >= 400) throw new TonyException(res.statusCode(), String.valueOf(out.get("detail")));
            return out;
        } catch (TonyException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("Tony request failed: " + e.getMessage(), e);
        }
    }

    public Map<String, Object> execute(String action, Map<String, Object> args, boolean approved) {
        return call("POST", "/v1/execute", Map.of("action", action, "args", args, "approved", approved));
    }

    public Map<String, Object> batch(List<Call> calls) {
        if (calls.size() > 20) throw new IllegalArgumentException("Batch is capped at 20 calls");
        return call("POST", "/v1/batch", Map.of("calls", calls));
    }

    public Map<String, Object> tools(String format) { return call("GET", "/v1/tools?fmt=" + format, null); }
    public Map<String, Object> connections() { return call("GET", "/v1/connections", null); }
    public Map<String, Object> connect(String app) { return call("POST", "/v1/connections/" + app + "/start", null); }
    public Map<String, Object> ask(String message) { return call("POST", "/v1/assistant", Map.of("message", message)); }

    public Map<String, Object> createSession(String entityId, List<String> apps, List<String> tiers, int ttlHours) {
        return call("POST", "/v1/sessions", Map.of("entity_id", entityId, "apps", apps,
                                                   "tiers", tiers, "ttl_hours", ttlHours));
    }
}
