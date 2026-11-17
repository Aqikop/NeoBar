"""Task and event schemas exchanged through Redis. Use Redis(decode_responses=True)."""
from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any, AsyncIterator, Protocol

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    SCAN = "scan"
    SEARCH = "search"


class EventType(str, Enum):
    ACCEPTED = "ACCEPTED"
    VISION_COMPLETED = "VISION_COMPLETED"
    SEARCH_RESULT = "SEARCH_RESULT"
    TOKEN = "TOKEN"
    DONE = "DONE"
    ERROR = "ERROR"


def new_task_id(task_type: TaskType) -> str:
    return f"{task_type.value}_{uuid.uuid4().hex[:12]}"


class Task(BaseModel):
    task_id: str
    type: TaskType
    payload: dict[str, Any] = Field(default_factory=dict)  # scan: {"blob_key": ...}; search: {"items": [...]}
    traceparent: str = ""  # W3C trace context, so worker spans join the API trace
    attempt: int = 0
    created_at: float = Field(default_factory=time.time)

    def to_fields(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "type": self.type.value,
            "payload": json.dumps(self.payload),
            "traceparent": self.traceparent,
            "attempt": str(self.attempt),
            "created_at": str(self.created_at),
        }

    @classmethod
    def from_fields(cls, f: dict[str, str]) -> "Task":
        return cls(
            task_id=f["task_id"],
            type=TaskType(f["type"]),
            payload=json.loads(f.get("payload") or "{}"),
            traceparent=f.get("traceparent", ""),
            attempt=int(f.get("attempt", 0)),
            created_at=float(f.get("created_at", time.time())),
        )


class Event(BaseModel):
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)

    def to_fields(self) -> dict[str, str]:
        return {"type": self.type.value, "data": json.dumps(self.data), "ts": str(self.ts)}

    @classmethod
    def from_fields(cls, f: dict[str, str]) -> "Event":
        return cls(type=EventType(f["type"]), data=json.loads(f.get("data") or "{}"), ts=float(f.get("ts", time.time())))


class TaskHandler(Protocol):
    """Contract between Dev 1 (worker loop) and Dev 2 (vision/search/solver).

    The worker loop iterates the generator and appends each Event to events_stream(task_id).
    Handlers must be idempotent: a task can be delivered more than once (at-least-once).
    Raise to signal failure; the loop handles retry/DLQ.
    """

    def handle(self, task: Task) -> AsyncIterator[Event]: ...