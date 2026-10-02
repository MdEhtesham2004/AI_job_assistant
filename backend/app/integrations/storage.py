"""File storage behind one interface (Phase 1 §5: files never live in the database).

`local` keeps files on disk (development and tests). An S3-compatible backend
(Cloudflare R2 / AWS S3) is added for production in Phase 14 — callers do not change.
"""

import asyncio
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.core.errors import NotFoundError

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.\-]{0,255}$")


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    content_type: str


class Storage(Protocol):
    name: str

    async def save(self, key: str, data: bytes, content_type: str) -> StoredFile: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def check(self) -> None:
        """Raise if the backend cannot store and read a file."""


def make_key(prefix: str, filename: str) -> str:
    """Unique, safe object key, e.g. `users/<id>/tasks/<uuid>-test.pdf`."""
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", filename)[:80] or "file"
    return f"{prefix.strip('/')}/{uuid.uuid4().hex}-{safe_name}"


class LocalStorage:
    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.match(key) or ".." in key.split("/"):
            raise ValueError(f"Invalid storage key: {key!r}")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"Storage key escapes the storage root: {key!r}")
        return path

    async def save(self, key: str, data: bytes, content_type: str) -> StoredFile:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)
        return StoredFile(key=key, size=len(data), content_type=content_type)

    async def read(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError("File not found.")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(lambda: path.unlink(missing_ok=True))

    async def check(self) -> None:
        key = f"healthcheck/{uuid.uuid4().hex}.txt"
        await self.save(key, b"ok", "text/plain")
        if await self.read(key) != b"ok":
            raise RuntimeError("Storage read-back mismatch")
        await self.delete(key)


def create_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        root = Path(settings.storage_local_path)
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[2] / root  # relative to backend/
        return LocalStorage(root)
    raise RuntimeError("STORAGE_BACKEND=s3 is added in Phase 14; use 'local' for now.")
