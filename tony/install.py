"""Install page data: one-click setup for every MCP client, like Composio's Install tab.

Everything is generated from the caller's own base URL so a self-hosted Tony
hands out snippets that point at itself, never at a hard-coded host.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from .auth import workspace_from_request

router = APIRouter(prefix="/v1/install", tags=["install"])


def _base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def clients(base: str, key: str) -> list[dict[str, Any]]:
    mcp = f"{base}/mcp"
    hdr = {"Authorization": f"Bearer {key}"}
    return [
        {"id": "claude-code", "name": "Claude Code", "group": "Claude",
         "kind": "command", "snippet": f'claude mcp add --transport http tony {mcp} --header "Authorization: Bearer {key}"',
         "note": "Run once in your terminal."},
        {"id": "claude-desktop", "name": "Claude Desktop", "group": "Claude",
         "kind": "json", "file": "claude_desktop_config.json",
         "snippet": json.dumps({"mcpServers": {"tony": {"command": "npx",
                    "args": ["-y", "mcp-remote", mcp, "--header", f"Authorization:Bearer {key}"]}}}, indent=2),
         "note": "Settings, Developer, Edit Config, paste, restart."},
        {"id": "cursor", "name": "Cursor", "group": "Editors",
         "kind": "json", "file": ".cursor/mcp.json",
         "snippet": json.dumps({"mcpServers": {"tony": {"url": mcp, "headers": hdr}}}, indent=2),
         "note": "Project or global mcp.json."},
        {"id": "vscode", "name": "VS Code", "group": "Editors",
         "kind": "json", "file": ".vscode/mcp.json",
         "snippet": json.dumps({"servers": {"tony": {"type": "http", "url": mcp, "headers": hdr}}}, indent=2),
         "note": "Needs GitHub Copilot agent mode."},
        {"id": "windsurf", "name": "Windsurf", "group": "Editors",
         "kind": "json", "file": "~/.codeium/windsurf/mcp_config.json",
         "snippet": json.dumps({"mcpServers": {"tony": {"serverUrl": mcp, "headers": hdr}}}, indent=2),
         "note": "Cascade, MCP, Add server."},
        {"id": "codex", "name": "Codex", "group": "OpenAI",
         "kind": "toml", "file": "~/.codex/config.toml",
         "snippet": f'[mcp_servers.tony]\nurl = "{mcp}"\nhttp_headers = {{ Authorization = "Bearer {key}" }}',
         "note": "Append to config.toml."},
        {"id": "chatgpt", "name": "ChatGPT", "group": "OpenAI",
         "kind": "url", "snippet": mcp, "note": "Settings, Connectors, add a custom MCP server with this URL."},
        {"id": "python", "name": "Python SDK", "group": "Code",
         "kind": "python", "snippet": (
             "import requests\n"
             f'r = requests.post("{base}/v1/agent",\n'
             f'    headers={{"Authorization": "Bearer {key}"}},\n'
             '    json={"goal": "find my unread invoices and summarise them"})\n'
             'print(r.json()["answer"])'),
         "note": "Plain HTTPS, no SDK to install."},
        {"id": "curl", "name": "cURL", "group": "Code",
         "kind": "command", "snippet": (
             f'curl -X POST {base}/v1/execute \\\n  -H "Authorization: Bearer {key}" \\\n'
             '  -H "content-type: application/json" \\\n'
             '  -d \'{"action":"hackernews.top_stories","args":{}}\''),
         "note": "Fastest way to prove it works."},
    ]


@router.get("")
def install(request: Request, key: str = "tk_live_YOUR_KEY") -> dict[str, Any]:
    workspace_from_request(request)
    base = _base(request)
    safe = key if key.replace("_", "").isalnum() else "tk_live_YOUR_KEY"
    return {"base_url": base, "mcp_url": f"{base}/mcp", "clients": clients(base, safe),
            "cli": f"curl -fsSL {base}/install.sh | sh",
            "note": "Create a key under API keys, or mint a scoped agent token, then replace YOUR_KEY."}
