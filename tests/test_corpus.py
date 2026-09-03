import hashlib
import json
import re

from backend.core.config import PROJECT_ROOT


def test_artifact_integrity_and_provenance():
    artifact = json.loads((PROJECT_ROOT / "data/legal-corpus.json").read_text(encoding="utf-8"))
    expected = artifact["manifest"].pop("artifactSha256")
    canonical = json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"
    assert hashlib.sha256(canonical.encode()).hexdigest() == expected
    assert len(artifact["documents"]) >= 24
    assert len(artifact["chunks"]) >= 150
    assert artifact["manifest"]["creator"] == "TMQuan"
    assert artifact["manifest"]["license"] == "CC-BY-4.0"
    assert re.fullmatch("[a-f0-9]{40}", artifact["manifest"]["revision"])
    sources = {source["id"]: source for source in artifact["documents"]}
    assert len(sources) == len(artifact["documents"])
    assert len({chunk["id"] for chunk in artifact["chunks"]}) == len(artifact["chunks"])
    for chunk in artifact["chunks"]:
        assert chunk["sourceId"] in sources
        assert 20 < len(chunk["text"]) <= 1400
    for source in sources.values():
        assert source["sourceUrl"].startswith("https://vbpl.vn/")
        assert (
            sum(chunk["sourceId"] == source["id"] for chunk in artifact["chunks"])
            == source["chunkCount"]
        )


def test_repository_contains_no_provider_credential():
    pattern = re.compile("".join(["AI", "za[\\w-]{20,}|", "AQ", "\\.[A-Za-z0-9_-]{20,}"]))
    extensions = {
        ".py",
        ".ts",
        ".tsx",
        ".mjs",
        ".md",
        ".yaml",
        ".yml",
        ".json",
        ".jsonc",
        ".sql",
        ".css",
        ".svg",
    }
    roots = [
        ".github",
        "backend",
        "config",
        "docs",
        "frontend/src",
        "frontend/tests",
        "scripts",
        "src",
        "tests",
    ]
    excluded = {".wrangler", "__pycache__", "node_modules", "dist"}
    files = [
        PROJECT_ROOT / name
        for name in [
            "README.md",
            "pyproject.toml",
            ".env.example",
            "frontend/.env.example",
            "frontend/package.json",
            "frontend/package-lock.json",
            "data/legal-corpus.json",
        ]
    ]
    for root in roots:
        files.extend(
            file
            for file in (PROJECT_ROOT / root).rglob("*")
            if file.is_file()
            and file.suffix in extensions
            and not excluded.intersection(file.relative_to(PROJECT_ROOT).parts)
        )
    matches = [
        str(file.relative_to(PROJECT_ROOT))
        for file in files
        if pattern.search(file.read_text(encoding="utf-8"))
    ]
    assert not matches, f"Credential-like string in: {matches}"
