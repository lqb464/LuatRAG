import re

from backend.core.config import PROJECT_ROOT


def test_readme_has_utf8_and_repository_screenshots():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert not any(
        marker in readme for marker in ("\ufffd", "\u00c3\u00a1", "\u00e1\u00bb", "\u00e1\u00ba")
    )
    assert not re.search(
        r"https?://(?:[^/]*\.)?(?:chatgpt\.com|oaiusercontent\.com)|sandbox:", readme
    )
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
    assert len(images) == 6
    for path in images:
        assert path.startswith("docs/screenshots/") and path.endswith(".jpg")
        image = (PROJECT_ROOT / path).read_bytes()
        assert image[:3] == b"\xff\xd8\xff" and image[-2:] == b"\xff\xd9"
        assert len(image) > 10_000
    assert (PROJECT_ROOT / "docs/examples/demo-leave-policy.txt").is_file()
