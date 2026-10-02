# ADR-0008: Realtime topology

- Status: Accepted
- Date: 2026-10-02

## Decision

- `web` runs gunicorn with ASGI (uvicorn) workers: HTTP, SSE and — when nothing else is routed —
  WebSockets. `channels` runs Daphne as the dedicated WebSocket service (`/ws/`); a reverse proxy routes
  `/ws/` to it. Without a proxy (compose demo) browsers use `EVAC_REALTIME_URL` for WebSockets.
- Channel layer: Redis (`channels-redis`); in-memory for dev/tests.
- `apps.core.realtime.publish(event, type, data)` sends to the event group and appends to a short
  per-event ring buffer in the cache with a monotonic sequence number. Clients connect WebSocket first,
  fall back to SSE (`/sse/e/<slug>/`, `Last-Event-ID` resume) and finally long-poll (`/poll/e/<slug>/`).
  Realtime is best effort; durable state always lives in the database.
- Screens (Phase 1) get their own consumer with device-token auth; evacuation delivery adds signed
  messages and LAN fallbacks (ADR-0003).

## Consequences

- One extra small dependency set (`uvicorn`, `uvicorn-worker`) for ASGI workers.
- SSE connections are capped at ~55 s per request and resumed by the browser, which keeps worker
  occupancy predictable.
