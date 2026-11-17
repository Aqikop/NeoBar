# NeoBar Redis & Event Contract (Dev 1 <-> Dev 2)

All names live in `shared/neobar_common/keys.py`; schemas in `shared/neobar_common/models.py`.
Redis clients use `decode_responses=True`. Delivery is **at-least-once**: handlers must be idempotent.

## Keys

| Key | Type | TTL | Purpose |
|---|---|---|---|
| `neobar:stream:tasks` | Stream | MAXLEN ~100k | Task queue, consumer group `workers-group` |
| `neobar:stream:dlq` | Stream | none | Tasks that failed `MAX_ATTEMPTS` (3) |
| `neobar:task:{task_id}` | Hash | 1h | `status`, `type`, `created_at`, `attempt` |
| `neobar:events:{task_id}` | Stream | 1h | Per-task events; SSE reads from here |
| `neobar:blob:{task_id}` | String | 10 min | Scan image bytes (kept out of the task stream) |
| `neobar:idem:{key}` | String | 60s | `PENDING`, then the stored JSON response |
| `neobar:cache:{hash}` | String | 1h | Cached search result (canonical ingredient-set hash) |
| `neobar:leader` | String | 2s lease | Value = node id; `SET NX PX`, renewed by Lua |
| `neobar:leader:fence` | Counter | none | `INCR` on each acquisition (fencing token) |

## Task message (`XADD neobar:stream:tasks`)

Fields (all strings): `task_id`, `type` (`scan`|`search`), `payload` (JSON), `traceparent`, `attempt`, `created_at`.

- scan payload: `{"blob_key": "neobar:blob:scan_xxx"}`
- search payload: `{"items": [{"name": "Gin", "category": "base_spirit", "estimated_volume_ml": 500}, ...]}`

## Event message (`XADD neobar:events:{task_id}`)

Fields: `type`, `data` (JSON), `ts`.

| type | data | emitted by |
|---|---|---|
| `ACCEPTED` | `{}` | API, right after enqueue |
| `VISION_COMPLETED` | the DTO from PLAN.md section 8 (`detected_items`, `equipment_detected`) | scan handler |
| `SEARCH_RESULT` | `{"candidates": [...]}` | search handler |
| `TOKEN` | `{"text": "..."}` | LLM streaming |
| `DONE` | `{}` | worker loop, last event, always |
| `ERROR` | `{"message": "..."}` | worker loop after final failure |

A task is finished when a `DONE` or `ERROR` event exists. SSE closes after sending it.

## HTTP

| Route | Behaviour |
|---|---|
| `POST /api/v1/scan` | Header `Idempotency-Key`. Stores image blob, enqueues, returns `202 {"task_id": ...}` |
| `POST /api/v1/search` | Header `Idempotency-Key`. Body = confirmed items. Returns `202 {"task_id": ...}` |
| `GET /api/v1/tasks/{task_id}/stream` | SSE. `id:` = events stream entry id, `event:` = type, `data:` = JSON. Supports `Last-Event-ID` replay |
| `GET /health`, `GET /ready` | Liveness / readiness (Redis ping) |

Why not Pub/Sub: it drops messages for subscribers that connect late. The client calls POST, then opens
SSE, so events must be replayable. That is why events live in a stream.

## Handler interface (Dev 2 implements)

```python
class TaskHandler(Protocol):
    def handle(self, task: Task) -> AsyncIterator[Event]: ...
```

The worker loop appends every yielded event to `neobar:events:{task_id}`, appends `DONE`, then `XACK`s.
An exception triggers retry (`attempt + 1`), and after 3 attempts the task goes to the DLQ plus an `ERROR` event.
Use `task.task_id` as the idempotency key for any side effect.

## Worker loop rules (Dev 1)

1. Consume via `XREADGROUP` with consumer name = hostname.
2. Every node consumes; only the lease holder runs `XAUTOCLAIM` (min-idle 10s, every 3s).
3. Lease: `SET neobar:leader <node> NX PX 2000`, renew every 0.5s via Lua (`GET == node` then `PEXPIRE`),
   step down immediately if renew fails.