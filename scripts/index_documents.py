import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.rag.pipeline import RagPipeline

folder = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "documents")
index_path = ROOT / "data" / "index" / "store.json"
pipeline = RagPipeline(index_path)
files = [path for path in folder.rglob("*") if path.is_file() and path.name != ".gitkeep"]
if not files:
    print(f"Không tìm thấy tài liệu trong {folder}")
    raise SystemExit(0)
for path in files:
    try:
        count = pipeline.ingest_file(path)
        print(f"OK  {path.name}: {count} đoạn")
    except Exception as exc:
        print(f"ERR {path.name}: {exc}")
