import os
import tempfile

os.environ.setdefault("TONY_DATA_DIR", tempfile.mkdtemp(prefix="tony-test-"))
os.environ.setdefault("TONY_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("TONY_DEMO_OPEN", "1")
os.environ.setdefault("TONY_REQUIRE_APPROVAL", "1")
os.environ.setdefault("TONY_ENV", "test")

import pytest

from tony.db import init_db


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from tony.main import app

    with TestClient(app) as c:
        yield c
