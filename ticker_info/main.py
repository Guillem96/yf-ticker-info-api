import datetime
from pathlib import Path
from typing import Literal, Optional

import pydantic
import pydantic_settings
import yfinance as yf  # type: ignore
from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from ticker_info import utils


class Settings(pydantic_settings.BaseSettings):
    cache_dir: Path = Path(".cache")
    cache_disabled: bool = False


class TickerInfo(pydantic.BaseModel):
    price: float
    name: str
    ticker: str
    yearly_dividend_yield: Optional[float]
    next_dividend_yield: float
    website: Optional[str]
    currency: Literal["EUR", "USD", "GBp"]
    ex_dividend_date: Optional[datetime.date]
    earning_dates: list[datetime.datetime]
    sector: str
    country: str
    industry: str
    is_etf: bool


class TickerNotFoundError(Exception):
    def __init__(self, ticker: str) -> None:
        super().__init__(f"{ticker} not found")


app = FastAPI()
settings = Settings()


@app.get("/{ticker}")
def get_ticker_info(ticker: str) -> TickerInfo:
    return _get_ticker_info(ticker)


@app.exception_handler(TickerNotFoundError)
async def ticker_not_found_err_handler(
    _: Request,
    exc: TickerNotFoundError,
) -> JSONResponse:
    return JSONResponse({"message": str(exc)}, status_code=404)


@utils.cache_to_file(
    base_dir=settings.cache_dir,
    ttl=60 * 60 * 24,  # Day in seconds
    disable=settings.cache_disabled,
)
def _get_ticker_info(ticker: str) -> TickerInfo:
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.get_info()
    if info == {"trailingPegRatio": None}:
        raise TickerNotFoundError(ticker)

    calendar = yf_ticker.get_calendar()
    price = info.get("currentPrice") or info["navPrice"]

    try:
        next_dividend_yield = round(
            info.get("lastDividendValue", info["trailingAnnualDividendRate"])
            / price,
            3,
        )
    except KeyError:
        next_dividend_yield = info.get("dividendYield", 0)

    return TickerInfo(
        name=info.get("shortName", ""),
        ticker=ticker,
        price=price,
        yearly_dividend_yield=info.get("dividendYield"),
        next_dividend_yield=next_dividend_yield,
        currency=info["currency"],
        sector=info.get("sectorDisp", ""),
        earning_dates=calendar.get("Earnings Date", []),
        website=info.get("website"),
        country=info.get("country", ""),
        industry=info.get("industryDisp", ""),
        is_etf=info.get("quoteType") == "ETF",
        ex_dividend_date=datetime.date.fromtimestamp(info["exDividendDate"])  # noqa: DTZ012
        if "exDividendDate" in info
        else None,
    )
