import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app


@pytest.fixture
def app(tmp_path):
    async def no_provider(**_kwargs):
        raise AssertionError("Unexpected Gemini call")

    return create_app(Settings(data_dir=tmp_path), generator=no_provider)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client
