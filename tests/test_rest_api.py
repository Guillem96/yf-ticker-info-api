import pytest
from fastapi.testclient import TestClient


def test_ticker_not_found(fastapi_test_client: TestClient) -> None:
    res = fastapi_test_client.get("/does-not-exist")
    assert res.status_code == 404


@pytest.mark.parametrize("ticker", ["TEF.MC", "COL.MC"])
def test_valid_eur_ticker(fastapi_test_client: TestClient, ticker: str) -> None:
    res = fastapi_test_client.get(f"/{ticker}")
    assert res.json()["currency"] == "EUR"
