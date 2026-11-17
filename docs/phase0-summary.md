# NeoBar Phase 0: Summary (Dev 1, Distributed Core & Infrastructure)

**Date:** 2026-11-17  
**Branch:** `phase0/setup`  
**Scope:** Harden the Day 1 scaffold so step 4 (API routes, idempotency, stream producer) can start on a solid base.

## 1. Starting point (Day 1)

The scaffold matched PLAN.md: `gateway/`, `services/{api,workers,etl}/`, `mobile/`, `data/`, `benchmarks/`, a compose file with Nginx, Redis (AOF on), Qdrant, Jaeger, an API stub with `/health`, and an idle worker loop. The dataset `data/cocktails_clean.json` held 426 drinks.

## 2. Problems found in review

| # | Problem | Why it mattered |
|---|---------|-----------------|
| 1 | No healthchecks; `depends_on` didn't wait for readiness | API or workers could start before Redis accepted connections; Nginx could crash if `api` wasn't resolvable yet |
| 2 | SSE route in Nginx (`/api/v1/tasks/{id}/stream`) differed from PLAN.md (`/stream/{task_id}`) | Mobile and backend would disagree on the path |
| 3 | Nginx rate limit fixed at `30r/m` per IP | k6 from one machine would get 429s immediately |
| 4 | Inconsistent key prefixes (`barvision:` vs `neobar:`) | Keys would be scattered and easy to mistype |
| 5 | No shared code between api and workers | Key names, task and event schemas would be duplicated |
| 6 | No `.dockerignore` | Whole repo (including `.git` and dataset) sent as build context |
| 7 | Unpinned dependencies; Redis OpenTelemetry package missing; PyTorch pulled into every worker build | Non-reproducible, slow builds, tracing step blocked |
| 8 | `/health` didn't check Redis | Healthchecks couldn't detect a dead dependency |
| 9 | `container_name` on workers | Blocked `docker compose up --scale worker=N` |

## 3. Changes made (15 files)

### New (8)
- `.dockerignore`: excludes `.git`, `data`, `docs`, `mobile`, `benchmarks`, tests, caches.
- `gateway/default.conf.template`: Nginx config rendered by envsubst; rate limit from `API_RATE` / `API_BURST`; SSE location with buffering off; 5M upload cap.
- `docs/contracts.md`: Redis and event contract between Dev 1 and Dev 2 (see section 4).
- `shared/neobar_common/__init__.py`: empty; marks the shared package.
- `shared/neobar_common/keys.py`: every Redis key, stream name, TTL and tunable under one `neobar:` prefix.
- `shared/neobar_common/models.py`: `Task`, `Event`, `TaskType`, `EventType`, `new_task_id`, and the `TaskHandler` protocol.
- `tests/test_common.py`: roundtrip tests for task and event serialization.
- `services/workers/requirements-ml.txt`: ML dependencies, installed only with `WITH_ML=true`.

### Replaced (7)
- `docker-compose.yml`: healthchecks, `service_healthy` conditions, pinned images (Nginx 1.27, Redis 7.4, Qdrant 1.12.4, Jaeger 1.62.0), one scalable `worker` service (2 replicas), `WITH_ML` build arg, env-driven rate limit.
- `services/api/src/main.py`: Redis client in lifespan; `/health` (liveness) and `/ready` (Redis ping, 503 on failure).
- `services/api/Dockerfile`, `services/workers/Dockerfile`: copy `shared/neobar_common` into the image; workers install core requirements always and ML only on demand.
- `services/api/requirements.txt`, `services/workers/requirements.txt`: pinned versions, added `opentelemetry-instrumentation-redis`.
- `services/workers/src/main.py`: node id falls back to container hostname.

### Deleted (1)
- `gateway/nginx.conf`: replaced by the template.

## 4. Design decisions recorded

- **Delivery semantics:** at-least-once. Handlers must be idempotent, keyed on `task_id`. "Zero task loss" does not mean exactly-once.
- **Events use a per-task Redis stream, not Pub/Sub** (`neobar:events:{task_id}`). Pub/Sub drops messages for late subscribers, and the client calls POST first and then opens SSE. SSE replays via `Last-Event-ID`.
- **No "NACK" in Redis Streams:** retries use an `attempt` counter, then a dead-letter stream after 3 attempts.
- **Leader lease:** `SET NX PX 2000`, renewed every 0.5s with a Lua check, with a fencing counter. A 2s TTL is what makes failover under 3s achievable (the original 5s TTL could not).
- **Only the leader runs `XAUTOCLAIM`** (min-idle 10s, every 3s); every node consumes tasks.
- **Scan images are stored as blobs** (`neobar:blob:{task_id}`, 10 min TTL) instead of travelling through the task stream.
- **Stream route:** `GET /api/v1/tasks/{task_id}/stream`.

### Key schema (from `keys.py`)

| Key | Type | TTL |
|---|---|---|
| `neobar:stream:tasks` | Stream | MAXLEN ~100k |
| `neobar:stream:dlq` | Stream | none |
| `neobar:task:{id}` | Hash | 1h |
| `neobar:events:{id}` | Stream | 1h |
| `neobar:blob:{id}` | String | 10 min |
| `neobar:idem:{key}` | String | 60s |
| `neobar:cache:{hash}` | String | 1h |
| `neobar:leader` | String | 2s lease |
| `neobar:leader:fence` | Counter | none |

## 5. Verification

Run on the developer machine after copying the changes:

| Check | Result |
|---|---|
| `docker compose up -d --build` | All services started |
| `docker compose ps` | `api`, `redis`, `qdrant` healthy; gateway and Jaeger up (no healthcheck defined for them) |
| `docker compose stop redis`, then `curl localhost:8000/ready` | `not_ready`, Redis unreachable |
| `docker compose start redis`, then `curl -i localhost:8000/ready` | `HTTP 200`, ready again |
| `git status` | Matched the expected 15 changes after fixing a `.text` filename typo |

Not yet confirmed: `PYTHONPATH=shared pytest tests` and the `WITH_ML=true` build.

## 6. Open items

- Rename `docs/Contracts.md` to `docs/contracts.md` (`git mv`, needed on case-insensitive filesystems).
- Reword README claims ("99.98% availability", "Raft-Inspired", "sub-30ms", "Redis Cluster") as targets until benchmarks produce numbers. A Redis lease is not Raft, and compose runs a single Redis node.
- Add a gateway healthcheck (optional).
- Push `phase0/setup` and open a PR.

## 7. Notes for Dev 2

- Implement `TaskHandler` from `neobar_common.models` and read `docs/contracts.md`.
- Pin the packages in `requirements-ml.txt`.
- `cocktails_clean.json` has 426 drinks, not the 600+ in the plan. In the first record, `measure_ml` looks flat at `45.0` regardless of the raw measure (for example "1 3/4 shot" gin and "1/4 shot" lemon juice), and Grand Marnier is typed `garnish`. Check the ml parsing before the solver is built, since ABV and bottleneck results depend on it.

## 8. Next: step 4

API routes (`/scan`, `/search`, `/tasks/{id}/stream`), Pydantic request models, the idempotency middleware (`SET idem:{key} PENDING NX EX 60`, then store the response), and the Redis Streams producer. Open question: put routes in `services/api/src/routes/` (matches PLAN.md, recommended) or keep them in `main.py` for now.
