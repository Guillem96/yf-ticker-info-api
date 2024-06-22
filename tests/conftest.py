import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fastapi_test_client() -> Iterator[TestClient]:
    from ticker_info import app

    prev_env = os.environ.copy()

    os.environ["CACHE_DISABLED"] = "true"
    yield TestClient(app)
    os.environ.clear()
    os.environ.update(prev_env)
