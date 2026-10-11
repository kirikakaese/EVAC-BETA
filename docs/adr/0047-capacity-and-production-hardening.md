# ADR-0047: Capacity (1,000 screens) and production hardening

- Status: Accepted
- Date: 2026-10-11

## Context

The Phase 9 gate is 1,000 simulated screens; brief §13 asks for 1,000 screens per instance. The earlier load test
(`scripts/load_ws.py`: 500 WebSocket players, alarm only) ran one process on SQLite. Phase 9 tests the deployed shape:
gunicorn with ASGI workers, daphne for WebSockets, a Celery worker, Redis and PostgreSQL
(`scripts/load_screens.py --production`). Each simulated screen boots like the player (configuration, program,
content bundle, evacuation state), holds its WebSocket, sends heartbeats, refetches its program after an
announcement and receives an alarm.

Running it found defects that only appear in production shape:

1. **PostgreSQL refused alarms**: `select_for_update()` together with `select_related` on a nullable foreign key
   (`EvacState.zone`, `EvacRequest.zone`) makes PostgreSQL fail with "FOR UPDATE cannot be applied to the
   nullable side of an outer join". Every alarm through the API or the two-person approval answered 500 on
   PostgreSQL. CI ran these paths on SQLite only.
2. **Database connections ran out**: under ASGI each request runs in its own thread, so persistent connections
   (`CONN_MAX_AGE=60`) accumulated until PostgreSQL refused clients.
3. **WebSocket consumers were dropped**: redis-py 8 sets a 5 s socket timeout by default, exactly channels_redis's
   5 s blocking pop, so idle consumers raced their own read timeout and crashed.
4. **Redis connection cap**: redis-py 8 also caps a pool at 100 connections and fails at once; hundreds of screens
   joining their groups after a reconnect exceeded it.
5. **Alarms silently dropped**: channels_redis keeps every message for the consumers of one WebSocket process under
   one Redis key with a capacity of 100 and `group_send` drops the rest without an error. An alarm to 1,000 screens
   reached about 150 of them.
6. **Slow fan-out**: one `group_send` per screen, all concurrent on a fresh event loop, opened up to 1,000 Redis
   connections per alarm (each with redis-py 8's handshake); sequence numbers cost two cache round trips per screen.
   An alarm request took 7 s.
7. **One WebSocket process** (daphne) could not hand 1,000 messages to its sockets within the 2 s target, and spent
   most of its time on heartbeats (two queries and two thread hops each, 100 per second).
8. **Refetch storm**: after a content change every screen asked for its program in the same second; an alarm
   arriving then waited behind 1,000 requests.

## Decision

- Lock only the locked table: `select_for_update(of=("self",))` where a nullable relation is joined.
- PostgreSQL uses psycopg's connection pool (Django 5.1+): `CONN_MAX_AGE=0`, at most `DB_POOL_MAX` (default 10)
  connections per process; `DB_POOL=0` switches pooling off. Dependency `psycopg[binary,pool]`.
- Channel layer connections get `socket_timeout=30` (well above the 5 s blocking pop); Redis pools for the cache
  and the channel layer allow `REDIS_MAX_CONNECTIONS` (default 1,000).
- Channel-layer `capacity` 20,000 (`CHANNEL_CAPACITY`). Fan-out to many screens (`channel.send_many`) uses one
  pipelined round trip for the group members of all screens and one Lua call for all messages (the script
  channels_redis runs per group), with a bounded per-screen fallback for other layers; sequence numbers come from
  one pipelined `INCR` round trip; dropped messages are logged.
- The realtime service runs as gunicorn with ASGI (uvicorn) workers, `WS_WORKERS` (default 3) processes sharing
  port 8001, like the web service; daphne stays for `runserver` in development.
- A heartbeat is one query (the update also checks the screen is still paired); the interval is cached.
- `program.changed` to more than 50 screens carries `spread` (seconds, 20 refetches per second, at most 60); players
  refetch at a random moment within it without blocking their WebSocket.
- After a state change the screens' fan-out is registered first on commit, before webhooks and the ops log.
- New CI jobs: *screens load (1,000 simulated screens, production shape)* with PostgreSQL and Redis services, and
  *tests on PostgreSQL* for the alarm, content, helpdesk and playback tests (`TEST_DATABASE_URL`).
- Measured on a 4-core machine that also runs the simulated screens: alarm p95 1.8 s, content change p95 1.5 s,
  refetch p95 0.2 s, heartbeat p95 15 ms, fleet boot 65–85 s.
- Targets of the load test (p95 over all screens):
  - **alarm** to every screen ≤ 2 s, **content change** pushed ≤ 2 s, program **refetch** ≤ 5 s,
    **heartbeat** acknowledgement ≤ 1 s;
  - **boot** is a cold start of all 1,000 screens in the same second (after a power cut). Players show their
    cached content and alarm bundle meanwhile, so it is a throughput target: the whole fleet within 180 s, each
    screen within 30 s (p95).
- The evacuation state and bundle are not cached between requests to make boots cheaper: a stale alarm bundle is a
  safety risk, and the measured boot wave is acceptable.

## Consequences

- PostgreSQL deployments must keep processes × `DB_POOL_MAX` below `max_connections` (documented in the handbook,
  *Monitoring → Capacity*).
- The load test needs about ten minutes of CI time; it runs after the main test job.

## Alternatives considered

- **More daphne processes behind the proxy**: needs a load-balancing proxy configuration on every install; gunicorn
  shares one port between workers without one.

- **PgBouncer** in front of PostgreSQL: another service to run at the venue; the built-in pool solves the leak.
- **Caching per-screen evacuation payloads**: faster boots, but invalidation errors would show wrong exits.
