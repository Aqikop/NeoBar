from neobar_common.models import Event, EventType, Task, TaskType, new_task_id


def test_task_roundtrip():
    t = Task(task_id=new_task_id(TaskType.SCAN), type=TaskType.SCAN,
             payload={"blob_key": "neobar:blob:x"}, traceparent="00-abc-def-01")
    assert Task.from_fields(t.to_fields()) == t


def test_event_roundtrip():
    e = Event(type=EventType.TOKEN, data={"text": "hi"})
    assert Event.from_fields(e.to_fields()) == e


def test_task_id_prefix():
    assert new_task_id(TaskType.SEARCH).startswith("search_")