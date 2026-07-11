from __future__ import annotations

import json
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Iterator, Protocol

from .models import RunEvent, StorageLoadResult


class StorageError(RuntimeError):
    code = "STORAGE_ERROR"


class StorageWriteError(StorageError):
    code = "STORAGE_WRITE_FAILED"


class StorageCorruptionError(StorageError):
    code = "STORAGE_CORRUPTED"


class StorageLockError(StorageError):
    code = "STORAGE_LOCK_FAILED"


class StorageNotFoundError(StorageError):
    code = "STORAGE_NOT_FOUND"


class StorageBackend(Protocol):
    def append(self, run_id: str, event: RunEvent) -> RunEvent: ...
    def load(self, run_id: str) -> StorageLoadResult: ...
    def delete(self, run_id: str) -> bool: ...
    def purge(self) -> int: ...


class InMemoryStorageBackend:
    def __init__(self) -> None:
        self._events: dict[str, list[RunEvent]] = {}
        self._lock = RLock()

    def append(self, run_id: str, event: RunEvent) -> RunEvent:
        if event.sequence is not None or event.run_id != run_id:
            raise StorageWriteError("event must match run and omit sequence")
        with self._lock:
            events = self._events.setdefault(run_id, [])
            stored = replace(event, sequence=len(events) + 1)
            events.append(stored)
            return stored

    def load(self, run_id: str) -> StorageLoadResult:
        with self._lock:
            if run_id not in self._events:
                raise StorageNotFoundError(run_id)
            return StorageLoadResult(tuple(self._events[run_id]))

    def delete(self, run_id: str) -> bool:
        with self._lock:
            return self._events.pop(run_id, None) is not None

    def purge(self) -> int:
        with self._lock:
            count = len(self._events)
            self._events.clear()
            return count


class JSONLStorageBackend:
    def __init__(self, root: Path, lock_timeout: float = 5.0) -> None:
        self._root = root
        self._lock_timeout = lock_timeout

    def append(self, run_id: str, event: RunEvent) -> RunEvent:
        if event.sequence is not None or event.run_id != run_id:
            raise StorageWriteError("event must match run and omit sequence")
        path = self._event_path(run_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._run_lock(run_id):
                if path.exists():
                    loaded = self._load_path(path)
                    sequence = loaded.events[-1].sequence + 1 if loaded.events else 1
                else:
                    sequence = 1
                stored = replace(event, sequence=sequence)
                encoded = json.dumps(stored.to_dict(), ensure_ascii=False, separators=(",", ":"))
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(encoded + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                return stored
        except StorageError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise StorageWriteError("failed to append run event") from exc

    def load(self, run_id: str) -> StorageLoadResult:
        path = self._event_path(run_id)
        if not path.exists():
            raise StorageNotFoundError(run_id)
        with self._run_lock(run_id):
            return self._load_path(path)

    def delete(self, run_id: str) -> bool:
        directory = self._root / run_id
        if not directory.exists():
            return False
        with self._run_lock(run_id):
            shutil.rmtree(directory)
        return True

    def purge(self) -> int:
        if not self._root.exists():
            return 0
        count = 0
        for directory in list(self._root.iterdir()):
            if directory.is_dir():
                if self.delete(directory.name):
                    count += 1
        return count

    def _load_path(self, path: Path) -> StorageLoadResult:
        raw = path.read_bytes()
        warnings: list[str] = []
        lines = raw.splitlines(keepends=True)
        if lines and not lines[-1].endswith((b"\n", b"\r")):
            lines.pop()
            warnings.append("TRUNCATED_TAIL")
        events: list[RunEvent] = []
        expected = 1
        for line in lines:
            try:
                value = json.loads(line.decode("utf-8"))
                event = RunEvent.from_dict(value)
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise StorageCorruptionError("invalid JSONL event") from exc
            if event.sequence != expected:
                raise StorageCorruptionError("invalid event sequence")
            expected += 1
            events.append(event)
        return StorageLoadResult(tuple(events), tuple(warnings))

    def _event_path(self, run_id: str) -> Path:
        if not run_id or run_id in {".", ".."} or Path(run_id).name != run_id:
            raise StorageWriteError("invalid run_id")
        return self._root / run_id / "events.jsonl"

    @contextmanager
    def _run_lock(self, run_id: str) -> Iterator[None]:
        lock_path = self._root / f".{run_id}.lock"
        deadline = time.monotonic() + self._lock_timeout
        fd: int | None = None
        while fd is None:
            try:
                self._root.mkdir(parents=True, exist_ok=True)
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise StorageLockError(run_id)
                time.sleep(0.01)
        try:
            yield
        finally:
            os.close(fd)
            lock_path.unlink(missing_ok=True)

