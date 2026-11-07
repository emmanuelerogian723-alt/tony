"""Tony CLI: serve, browse the catalogue, run actions, scaffold new apps."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys

TEMPLATE = """slug: {slug}
name: {name}
category: Other
description: One line about what this app does.
docs: https://example.com/api-docs
logo: https://cdn.simpleicons.org/{slug}/000000
auth:
  type: bearer          # oauth2 | bearer | api_key | basic | path | none
  client_id_env: {upper}_CLIENT_ID
  client_secret_env: {upper}_CLIENT_SECRET
  authorize_url: https://example.com/oauth/authorize
  token_url: https://example.com/oauth/token
  scopes: []
actions:
  - slug: whoami
    name: Who am I
    description: Return the signed-in account.
    method: GET
    url: https://api.example.com/v1/me
    tier: read
    response:
      max_chars: 4000
"""


def _catalog():
    from .catalog import catalog

    return catalog


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "tony.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def cmd_apps(args: argparse.Namespace) -> int:
    cat = _catalog()
    apps = cat.search(args.search, args.category)
    if args.json:
        print(json.dumps([a.to_dict(include_actions=False) for a in apps], indent=2))
        return 0
    width = max((len(a.slug) for a in apps), default=10)
    print(f"{'APP'.ljust(width)}  {'ACTIONS':>7}  {'AUTH':<8}  NAME")
    for app in apps:
        print(f"{app.slug.ljust(width)}  {len(app.actions):>7}  {app.auth.type:<8}  {app.name}")
    print(f"\n{len(apps)} apps · {sum(len(a.actions) for a in apps)} actions")
    return 0


def cmd_actions(args: argparse.Namespace) -> int:
    cat = _catalog()
    if args.app:
        apps = [cat.get(args.app)]
    else:
        apps = list(cat.apps.values())
    rows = []
    for app in apps:
        for action in app.actions:
            if args.search and args.search.lower() not in f"{action.slug} {action.name} {action.description}".lower():
                continue
            rows.append((app.slug, action))
    if args.json:
        print(json.dumps([{"action": f"{a.slug}.{act.slug}", **act.to_dict()} for a, act in rows], indent=2))
        return 0
    for app_slug, action in rows:
        print(f"{app_slug}.{action.slug:<24} {action.tier:<9} {action.name}")
    print(f"\n{len(rows)} actions")
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    from .executor import execute

    cat = _catalog()
    app_slug, _, action_slug = args.action.partition(".")
    if not action_slug:
        print("Action must look like app.action (e.g. hackernews.top_stories)", file=sys.stderr)
        return 2
    spec = cat.get(app_slug)
    action = spec.action(action_slug)
    payload = {}
    for pair in args.arg or []:
        key, _, raw = pair.partition("=")
        try:
            payload[key] = json.loads(raw)
        except json.JSONDecodeError:
            payload[key] = raw
    result = asyncio.run(execute(spec, action, payload, None, dry_run=args.dry_run))
    print(json.dumps(result.as_dict(), indent=2, default=str))
    return 0 if result.ok else 1


def cmd_new_app(args: argparse.Namespace) -> int:
    slug = args.slug.strip().lower().replace("-", "_")
    path = os.path.join(os.path.dirname(__file__), "apps", f"{slug}.yaml")
    if os.path.exists(path) and not args.force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return 2
    name = args.name or slug.replace("_", " ").title()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE.format(slug=slug, name=name, upper=slug.upper()))
    print(f"wrote {path}\nnext: fill in the auth + actions, then run `tony apps --search {slug}`")
    return 0


def cmd_keygen(args: argparse.Namespace) -> int:
    print(secrets.token_hex(32))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from .catalog import catalog

    tools = []
    for app in catalog.apps.values():
        for action in app.actions:
            if args.app and app.slug != args.app:
                continue
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"{app.slug}__{action.slug}",
                        "description": action.description or action.name,
                        "parameters": {"type": "object", "properties": action.params, "required": action.required},
                    },
                }
            )
    print(json.dumps(tools, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tony", description="Open-source integration gateway for AI agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the Tony server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--log-level", default="info")
    serve.set_defaults(func=cmd_serve)

    apps = sub.add_parser("apps", help="List apps in the catalogue")
    apps.add_argument("--search", default="")
    apps.add_argument("--category", default="")
    apps.add_argument("--json", action="store_true")
    apps.set_defaults(func=cmd_apps)

    actions = sub.add_parser("actions", help="List actions")
    actions.add_argument("--app", default="")
    actions.add_argument("--search", default="")
    actions.add_argument("--json", action="store_true")
    actions.set_defaults(func=cmd_actions)

    execute = sub.add_parser("execute", help="Run an action locally")
    execute.add_argument("action", help="app.action")
    execute.add_argument("--arg", action="append", help="key=value (repeatable)")
    execute.add_argument("--dry-run", action="store_true")
    execute.set_defaults(func=cmd_execute)

    new_app = sub.add_parser("new-app", help="Scaffold a manifest")
    new_app.add_argument("slug")
    new_app.add_argument("--name", default="")
    new_app.add_argument("--force", action="store_true")
    new_app.set_defaults(func=cmd_new_app)

    keygen = sub.add_parser("keygen", help="Generate a TONY_SECRET_KEY")
    keygen.set_defaults(func=cmd_keygen)

    export = sub.add_parser("export-tools", help="OpenAI-style tool schemas as JSON")
    export.add_argument("--app", default="")
    export.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
