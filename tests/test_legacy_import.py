import sqlite3
from contextlib import closing

import pytest

from backend.src.sources import create_source
from backend.src.store import Store
from scripts.migrate_legacy_storage import migrate


def test_legacy_import_preserves_original_db_and_both_objects(tmp_path):
    original = Store(tmp_path / "original")
    original.initialize()
    source = create_source(
        original,
        "user-1",
        "policy.txt",
        "text/plain",
        b"An internal policy with sufficient text to index safely.",
    )
    state = tmp_path / "legacy"
    d1 = state / "d1/worker"
    r2 = state / "r2/worker"
    blobs = state / "r2/luatrag-local/blobs"
    for directory in (d1, r2, blobs):
        directory.mkdir(parents=True)
    with original.connect() as db, closing(sqlite3.connect(d1 / "state.sqlite")) as legacy:
        db.backup(legacy)
        keys = db.execute("SELECT r2_key, extracted_key FROM sources").fetchone()
    with closing(sqlite3.connect(r2 / "state.sqlite")) as bucket:
        bucket.execute(
            "CREATE TABLE _mf_objects (key TEXT PRIMARY KEY, blob_id TEXT, size INTEGER)"
        )
        for index, key in enumerate(keys):
            value = original.get_object(key)
            (blobs / str(index)).write_bytes(value)
            bucket.execute(
                "INSERT INTO _mf_objects VALUES (?, ?, ?)", (key, str(index), len(value))
            )
        bucket.commit()
    target = tmp_path / "new-runtime"
    assert migrate(state, target) == {"sources": 1, "conversations": 0, "objects": 2}
    migrated = Store(target)
    for key in keys:
        assert migrated.get_object(key) == original.get_object(key)
    with original.connect() as db:
        assert db.execute("SELECT id FROM sources").fetchone()[0] == source["id"]
    with migrated.connect() as db:
        assert db.execute("SELECT id FROM sources").fetchone()[0] == source["id"]
    with pytest.raises(RuntimeError, match="exists"):
        migrate(state, target)
