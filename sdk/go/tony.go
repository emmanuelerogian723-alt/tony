// Package tony is a dependency-free client for the Tony integration gateway.
//
//	client := tony.New(os.Getenv("TONY_KEY"))
//	res, err := client.Execute(ctx, "github.list_repos", map[string]any{"per_page": 3})
package tony

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

const DefaultBaseURL = "https://tony-7su0.onrender.com"

type Client struct {
	APIKey  string
	BaseURL string
	Session string
	HTTP    *http.Client
}

func New(apiKey string) *Client {
	return &Client{APIKey: apiKey, BaseURL: DefaultBaseURL, HTTP: &http.Client{Timeout: 60 * time.Second}}
}

type Error struct {
	Status int
	Detail any
}

func (e *Error) Error() string { return fmt.Sprintf("tony: %d %v", e.Status, e.Detail) }

func (c *Client) do(ctx context.Context, method, path string, body any, out any) error {
	var buf io.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return err
		}
		buf = bytes.NewReader(raw)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, buf)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.APIKey)
	req.Header.Set("Content-Type", "application/json")
	if c.Session != "" {
		req.Header.Set("X-Tony-Session", c.Session)
	}
	res, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	raw, _ := io.ReadAll(res.Body)
	if res.StatusCode >= 400 {
		var payload map[string]any
		_ = json.Unmarshal(raw, &payload)
		return &Error{Status: res.StatusCode, Detail: payload["detail"]}
	}
	if out == nil || len(raw) == 0 {
		return nil
	}
	return json.Unmarshal(raw, out)
}

// Execute runs one action. Write actions return Status "pending_approval" until
// you call Execute again with approved=true.
func (c *Client) Execute(ctx context.Context, action string, args map[string]any, approved bool) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodPost, "/v1/execute", map[string]any{"action": action, "args": args, "approved": approved}, &out)
	return out, err
}

type Call struct {
	Action string         `json:"action"`
	Args   map[string]any `json:"args,omitempty"`
}

func (c *Client) Batch(ctx context.Context, calls []Call) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodPost, "/v1/batch", map[string]any{"calls": calls}, &out)
	return out, err
}

func (c *Client) Tools(ctx context.Context, format string) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodGet, "/v1/tools?fmt="+format, nil, &out)
	return out, err
}

func (c *Client) Connections(ctx context.Context) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodGet, "/v1/connections", nil, &out)
	return out, err
}

func (c *Client) Connect(ctx context.Context, app string) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodPost, "/v1/connections/"+app+"/start", nil, &out)
	return out, err
}

func (c *Client) CreateSession(ctx context.Context, entityID string, apps, tiers []string, ttlHours int) (map[string]any, error) {
	var out map[string]any
	body := map[string]any{"entity_id": entityID, "apps": apps, "tiers": tiers, "ttl_hours": ttlHours}
	err := c.do(ctx, http.MethodPost, "/v1/sessions", body, &out)
	return out, err
}

func (c *Client) Ask(ctx context.Context, message string) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodPost, "/v1/assistant", map[string]any{"message": message}, &out)
	return out, err
}
