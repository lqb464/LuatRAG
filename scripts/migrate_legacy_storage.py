"""Non-destructive import of local Wrangler D1/R2 state into the Python runtime."""

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from backend.core.config import Settings
from backend.src.store import Store


def read_only(path: Path):
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def find_database(directory: Path, table: str) -> Path:
    for path in directory.rglob("*.sqlite"):
        with closing(read_only(path)) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        if exists:
            return path
    raise RuntimeError(f"No legacy database with table {table} under {directory}")


def migrate(state_path: Path, data_dir: Path, bucket_name="luatrag-local") -> dict:
    store = Store(data_dir)
    if store.database_path.exists():
        raise RuntimeError("Target database exists; refusing to overwrite it.")
    original = read_only(find_database(state_path / "d1", "sources"))
    r2 = read_only(find_database(state_path / "r2", "_mf_objects"))
    blob_root = (state_path / "r2" / bucket_name / "blobs").resolve()
    source_keys = [
        key
        for row in original.execute("SELECT r2_key, extracted_key FROM sources")
        for key in row
        if key
    ]
    with tempfile.NamedTemporaryFile(dir=store.data_dir, suffix=".sqlite", delete=False) as stream:
        temporary = Path(stream.name)
    written = []
    try:
        for key in source_keys:
            row = r2.execute("SELECT blob_id, size FROM _mf_objects WHERE key=?", (key,)).fetchone()
            if row is None or not row[0]:
                raise RuntimeError(
                    "A referenced legacy object is missing; original state was not changed."
                )
            path = (blob_root / row[0]).resolve()
            if (
                not path.is_relative_to(blob_root)
                or not path.is_file()
                or path.stat().st_size != row[1]
            ):
                raise RuntimeError("A referenced legacy blob cannot be imported safely.")
            store.put_object(key, path.read_bytes())
            written.append(key)
        with closing(sqlite3.connect(temporary)) as target:
            original.backup(target)
            if target.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Legacy database failed foreign-key validation.")
        counts = {
            "sources": original.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "conversations": original.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            "objects": len(written),
        }
        os.replace(temporary, store.database_path)
        store.initialize()
        return counts
    except BaseException:
        for key in written:
            store.delete_object(key)
        raise
    finally:
        original.close()
        r2.close()
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-path", type=Path, default=Path("backend/.wrangler/state/v3"))
    parser.add_argument("--data-dir", type=Path, default=Settings.from_env().data_dir)
    parser.add_argument("--bucket-name", default="luatrag-local")
    args = parser.parse_args()
    print(migrate(args.state_path, args.data_dir, args.bucket_name))


if __name__ == "__main__":
    main()
