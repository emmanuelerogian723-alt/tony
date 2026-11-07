# Deployment

Tony is a single Python service. Anything that runs a container or a Python process works.

## Docker (recommended)

```bash
docker build -t tony .
docker run -p 8000:8000 --env-file .env -v tony-data:/data tony
```

`docker-compose.yml` adds Postgres:

```bash
docker compose up -d
```

## Render

`render.yaml` is included. Point Render at the repo and it provisions the service.
Set these env vars in the dashboard:

| Variable | Value |
|----------|-------|
| `TONY_BASE_URL` | `https://<your-service>.onrender.com` |
| `TONY_SECRET_KEY` | output of `tony keygen` |
| `TONY_ADMIN_TOKEN` | a long random string |
| `TONY_DEMO_OPEN` | `0` for a private instance, `1` to let visitors try public apps |
| `DATABASE_URL` | a Postgres URL — **required** if you want data to survive deploys |

> Render's free tier has an ephemeral disk. With no `DATABASE_URL`, Tony stores data in SQLite
> inside the container, and **workspaces, connections and runs are lost on every deploy**.
> Use a managed Postgres (Render, Supabase, Neon, Railway) before inviting real users.

## Railway / Fly.io / VPS

Same three steps: install `requirements.txt`, set env vars, run
`uvicorn tony.main:app --host 0.0.0.0 --port $PORT`. Put it behind TLS — OAuth redirect URIs
must be https in production.

## OAuth redirect URIs

For every app you enable, register this exact callback at the provider:

```
https://<your-domain>/oauth/callback
```

Tony builds the `state` value per session, so one callback serves every app.

## First run

1. Open `/app` — with `TONY_DEMO_OPEN=1` you land in a demo workspace immediately.
2. Or create a workspace: `POST /v1/workspaces` with `Authorization: Bearer $TONY_ADMIN_TOKEN`.
3. Copy the `tk_live_…` key it returns; that is the only time it is shown.
4. Try a keyless action: `POST /v1/execute {"action":"hackernews.top_stories"}`.
5. Connect a real app: `POST /v1/connections/github/start` and follow `authorization_url`.

## Health and scaling

* `GET /health` returns catalogue counts and manifest errors — wire it to your uptime monitor.
* The service is stateless apart from the database; scale horizontally behind a load balancer.
* Trigger polling runs inside the app. For more than a few hundred triggers, run a single
  dedicated worker (set `TONY_POLL_INTERVAL`) so polls never double-fire across replicas.
