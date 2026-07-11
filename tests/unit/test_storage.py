import json

import pytest

from oracle_council.models import RunEvent
from oracle_council.storage import (
    InMemoryStorageBackend,
    JSONLStorageBackend,
    StorageCorruptionError,
    StorageNotFoundError,
    StorageWriteError,
)


def event(run_id="run-1", event_type="run_created", payload=None):
    return RunEvent(run_id, event_type, payload or {})


class TestInMemory:
    def test_append_assigns_monotonic_sequence(self):
        storage = InMemoryStorageBackend()
        first = storage.append("run-1", event())
        second = storage.append("run-1", event(event_type="run_completed"))
        assert (first.sequence, second.sequence) == (1, 2)

    def test_append_rejects_preassigned_sequence_and_foreign_run(self):
        storage = InMemoryStorageBackend()
        with pytest.raises(StorageWriteError):
            storage.append("run-1", RunEvent("run-1", "x", {}, sequence=5))
        with pytest.raises(StorageWriteError):
            storage.append("run-1", event(run_id="run-2"))

    def test_load_delete_purge(self):
        storage = InMemoryStorageBackend()
        storage.append("run-1", event())
        assert len(storage.load("run-1").events) == 1
        assert storage.delete("run-1") is True
        assert storage.delete("run-1") is False
        storage.append("run-2", event(run_id="run-2"))
        assert storage.purge() == 1
        with pytest.raises(StorageNotFoundError):
            storage.load("run-2")


class TestJSONL:
    def test_round_trip_with_storage_owned_sequence(self, tmp_path):
        storage = JSONLStorageBackend(tmp_path)
        storage.append("run-1", event())
        storage.append("run-1", event(event_type="run_completed"))
        loaded = storage.load("run-1")
        assert [e.sequence for e in loaded.events] == [1, 2]
        assert loaded.events[1].event_type == "run_completed"
        assert loaded.warnings == ()

    def test_truncated_tail_is_dropped_with_warning(self, tmp_path):
        storage = JSONLStorageBackend(tmp_path)
        storage.append("run-1", event())
        path = tmp_path / "run-1" / "events.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write('{"run_id": "run-1", "event_type": "half')  # no newline
        loaded = storage.load("run-1")
        assert len(loaded.events) == 1
        assert "TRUNCATED_TAIL" in loaded.warnings

    def test_corrupted_line_raises(self, tmp_path):
        storage = JSONLStorageBackend(tmp_path)
        storage.append("run-1", event())
        path = tmp_path / "run-1" / "events.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("not-json\n")
        with pytest.raises(StorageCorruptionError):
            storage.load("run-1")

    def test_sequence_gap_raises(self, tmp_path):
        storage = JSONLStorageBackend(tmp_path)
        stored = storage.append("run-1", event())
        path = tmp_path / "run-1" / "events.jsonl"
        value = stored.to_dict()
        value["sequence"] = 9
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value) + "\n")
        with pytest.raises(StorageCorruptionError):
            storage.load("run-1")

    def test_delete_and_purge(self, tmp_path):
        storage = JSONLStorageBackend(tmp_path)
        storage.append("run-1", event())
        storage.append("run-2", event(run_id="run-2"))
        assert storage.delete("run-1") is True
        assert not (tmp_path / "run-1").exists()
        assert storage.purge() == 1

    def test_invalid_run_id_rejected(self, tmp_path):
        storage = JSONLStorageBackend(tmp_path)
        with pytest.raises(StorageWriteError):
            storage.append("../escape", event(run_id="../escape"))
