import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


_WINDOWS_INVALID_CHARS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class ArtifactStore:
    _locks_guard = threading.Lock()
    _destination_locks: dict[str, threading.Lock] = {}
    _publication_locks: dict[str, threading.Lock] = {}

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ValueError("Artifact path must be relative")
        if ".." in relative.parts:
            raise ValueError("Artifact path cannot contain parent traversal")
        for component in relative.parts:
            if (
                any(
                    character in _WINDOWS_INVALID_CHARS or ord(character) < 32
                    for character in component
                )
                or component.endswith((".", " "))
                or component.split(".", 1)[0].upper() in _WINDOWS_RESERVED_BASENAMES
            ):
                raise ValueError("Artifact path contains a non-portable component")

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
                    newline="\n",
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

    def publish_bytes_set(self, artifacts: dict[str, bytes]) -> dict[str, str]:
        destinations = {path: self.path(path) for path in artifacts}
        root_key = os.path.normcase(str(self.root))
        with self._locks_guard:
            publication_lock = self._publication_locks.setdefault(root_key, threading.Lock())

        with publication_lock:
            staged: dict[str, Path] = {}
            backups: dict[str, Path] = {}
            existed = {path: destination.exists() for path, destination in destinations.items()}
            committed: list[str] = []
            try:
                for path, destination in destinations.items():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    staged[path] = self._temporary_bytes(destination, artifacts[path], "stage")
                    if existed[path]:
                        backups[path] = self._temporary_bytes(
                            destination,
                            destination.read_bytes(),
                            "backup",
                        )

                for path, destination in destinations.items():
                    os.replace(staged[path], destination)
                    staged.pop(path)
                    committed.append(path)
            except BaseException:
                for path in reversed(committed):
                    destination = destinations[path]
                    if existed[path]:
                        os.replace(backups.pop(path), destination)
                    else:
                        destination.unlink(missing_ok=True)
                raise
            finally:
                for temporary in (*staged.values(), *backups.values()):
                    temporary.unlink(missing_ok=True)

        return {path: destination.relative_to(self.root).as_posix() for path, destination in destinations.items()}

    @staticmethod
    def _temporary_bytes(destination: Path, content: bytes, kind: str) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=destination.parent,
            prefix=f".{destination.name}.{kind}.",
            suffix=".tmp",
        ) as temporary:
            temporary.write(content)
            return Path(temporary.name)

    def write_json(self, relative_path: str | Path, content: Any) -> str:
        serialized = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        return self.write_text(relative_path, serialized)

    def read_text(self, relative_path: str | Path) -> str:
        return self.path(relative_path).read_text(encoding="utf-8")

    def read_json(self, relative_path: str | Path) -> Any:
        return json.loads(self.read_text(relative_path))
