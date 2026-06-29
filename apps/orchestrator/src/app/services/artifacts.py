import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


class ArtifactStore:
    _locks_guard = threading.Lock()
    _destination_locks: dict[str, threading.Lock] = {}

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ValueError("Artifact path must be relative")
        if ".." in relative.parts:
            raise ValueError("Artifact path cannot contain parent traversal")

        candidate = self.root / relative
        resolved = candidate.parent.resolve() / candidate.name
        if candidate.is_symlink():
            resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Artifact path must remain within the project root")
        return resolved

    def _destination_and_lock(
        self, relative_path: str | Path
    ) -> tuple[Path, threading.Lock]:
        destination = self.path(relative_path)
        key = os.path.normcase(str(destination))
        with self._locks_guard:
            lock = self._destination_locks.setdefault(key, threading.Lock())
        return destination, lock

    def write_text(self, relative_path: str | Path, content: str) -> str:
        destination, lock = self._destination_and_lock(relative_path)
        with lock:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    suffix=".tmp",
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    temporary.write(content)
                os.replace(temporary_path, destination)
            except BaseException:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise
            return destination.relative_to(self.root).as_posix()

    def write_json(self, relative_path: str | Path, content: Any) -> str:
        serialized = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        return self.write_text(relative_path, serialized)

    def read_text(self, relative_path: str | Path) -> str:
        return self.path(relative_path).read_text(encoding="utf-8")

    def read_json(self, relative_path: str | Path) -> Any:
        return json.loads(self.read_text(relative_path))
