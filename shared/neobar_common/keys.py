"""Single source of truth for every Redis key, stream and tunable shared by api and workers."""

PREFIX = "neobar"

# Streams / groups
TASK_STREAM = f"{PREFIX}:stream:tasks"
DLQ_STREAM = f"{PREFIX}:stream:dlq"
CONSUMER_GROUP = "workers-group"

# Leader election
LEADER_KEY = f"{PREFIX}:leader"
LEADER_FENCE_KEY = f"{PREFIX}:leader:fence"


def idem_key(idempotency_key: str) -> str:
    return f"{PREFIX}:idem:{idempotency_key}"


def task_key(task_id: str) -> str:
    """Hash with task status/metadata."""
    return f"{PREFIX}:task:{task_id}"


def events_stream(task_id: str) -> str:
    """Per-task event stream; SSE replays from here (replaces Pub/Sub)."""
    return f"{PREFIX}:events:{task_id}"


def blob_key(task_id: str) -> str:
    """Scan image bytes, kept out of the task stream."""
    return f"{PREFIX}:blob:{task_id}"


def cache_key(canonical_hash: str) -> str:
    return f"{PREFIX}:cache:{canonical_hash}"


# TTLs / limits
IDEMPOTENCY_TTL_S = 60
TASK_META_TTL_S = 3600
EVENTS_TTL_S = 3600
BLOB_TTL_S = 600
CACHE_TTL_S = 3600

STREAM_MAXLEN = 100_000
MAX_ATTEMPTS = 3

LEASE_TTL_MS = 2000
LEASE_RENEW_S = 0.5
RECLAIM_MIN_IDLE_MS = 10_000
RECLAIM_INTERVAL_S = 3