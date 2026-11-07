#!/usr/bin/env python3
"""Tony MCP stdio bridge.

Claude Desktop and other stdio-only MCP clients cannot speak HTTP directly.
This bridge forwards newline-delimited JSON-RPC to a Tony instance.

    TONY_URL=https://tony-7su0.onrender.com TONY_API_KEY=tk_live_... python tony_mcp.py

Claude Desktop config:

    {
      "mcpServers": {
        "tony": {
          "command": "python",
          "args": ["/absolute/path/to/tony_mcp.py"],
          "env": {"TONY_URL": "https://tony-7su0.onrender.com", "TONY_API_KEY": "tk_live_..."}
        }
      }
    }
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

DEFAULT_URL = "https://tony-7su0.onrender.com"


def client() -> tuple[str, str]:
    url = (os.getenv("TONY_URL") or DEFAULT_URL).rstrip("/")
    key = os.getenv("TONY_API_KEY", "")
    if not key:
        print("TONY_API_KEY is required", file=sys.stderr)
    return f"{url}/mcp", key


def forward(endpoint: str, key: str, message: dict) -> dict:
    data = json.dumps(message).encode()
    req = urllib.request.Request(endpoint, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        **({"Authorization": f"Bearer {key}"} if key else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read() or b"{}")
    except Exception as exc:  # surface the failure as a JSON-RPC error
        return {"jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": -32000, "message": f"Tony unreachable: {exc}"}}


def main() -> None:
    endpoint, key = client()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if "id" not in message:  # notifications get no answer
            forward(endpoint, key, message)
            continue
        print(json.dumps(forward(endpoint, key, message)), flush=True)


if __name__ == "__main__":
    main()
