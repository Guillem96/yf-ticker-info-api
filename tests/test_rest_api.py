import pytest
from fastapi.testclient import TestClient


def test_ticker_not_found(fastapi_test_client: TestClient) -> None:
    res = fastapi_test_client.get("/does-not-exist")
    assert res.status_code == 404


@pytest.mark.parametrize("ticker", ["TEF.MC", "COL.MC"])
def test_valid_eur_ticker(fastapi_test_client: TestClient, ticker: str) -> None:
    res = fastapi_test_client.get(f"/{ticker}")
    assert res.json()["currency"] == "EUR"


@pytest.mark.parametrize("ticker", ["IEMG"])
def test_valid_etfs(fastapi_test_client: TestClient, ticker: str) -> None:
    res = fastapi_test_client.get(f"/{ticker}")
    assert res.json()["is_etf"]


@pytest.mark.parametrize(
    "tickers",
    [["TEF.MC", "COL.MC"], ["SAN.MC", "HSY", "AAPL"]],
)
def test_valid_multiple_tickers(
    fastapi_test_client: TestClient,
    tickers: list[str],
) -> None:
    ts = ",".join(tickers)
    res = fastapi_test_client.get(f"/{ts}")
    res_content = res.json()
    assert len(res_content) == len(tickers)
    assert all(t["ticker"] == tr for t, tr in zip(res_content, tickers))
