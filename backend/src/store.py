import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def encode_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.data_dir / "luatrag.db"
        self.objects_dir = self.data_dir / "objects"
        self.objects_dir.mkdir(exist_ok=True)

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sources'"
            ).fetchone()
            if not exists:
                migration = Path(__file__).resolve().parents[1] / "migrations" / "0001_initial.sql"
                db.executescript(migration.read_text(encoding="utf-8"))
            db.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            db.execute(
                "INSERT OR IGNORE INTO schema_migrations VALUES ('0001_initial', ?)", (now_iso(),)
            )

    def object_path(self, key: str) -> Path:
        return self.objects_dir / hashlib.sha256(key.encode()).hexdigest()

    def put_object(self, key: str, value: bytes):
        target = self.object_path(key)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.objects_dir, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get_object(self, key: str) -> bytes | None:
        target = self.object_path(key)
        return target.read_bytes() if target.is_file() else None

    def delete_object(self, key: str):
        self.object_path(key).unlink(missing_ok=True)

    @staticmethod
    def audit(db, owner_id: str, action: str, source_id: str, metadata):
        db.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, 'source', ?, ?, ?)",
            (str(uuid4()), owner_id, action, source_id, encode_json(metadata), now_iso()),
        )
