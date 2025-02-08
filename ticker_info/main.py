import concurrent.futures
import datetime
from typing import Literal, Optional, Union

import pydantic
import pydantic_settings
import yfinance as yf  # type: ignore
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from ticker_info import utils


class Settings(pydantic_settings.BaseSettings):
    cache_dir: str = ".cache"
    cache_disabled: bool = False
    cache_ttl: int = 3600


class PriceRange(pydantic.BaseModel):
    high: float
    low: float


class TickerInfo(pydantic.BaseModel):
    price: float
    name: str
    ticker: str
    yearly_dividend_yield: Optional[float]
    next_dividend_yield: float
    yearly_dividend_value: Optional[float]
    next_dividend_value: Optional[float]
    website: Optional[str]
    currency: Literal["EUR", "USD", "GBp"]
    ex_dividend_date: Optional[datetime.date]
    earning_dates: list[datetime.datetime]
    sector: str
    country: str
    industry: str
    is_etf: bool
    monthly_price_range: PriceRange
    yearly_price_range: PriceRange


class TickerNotFoundError(Exception):
    def __init__(self, ticker: str) -> None:
        super().__init__(f"{ticker} not found")


app = FastAPI()
settings = Settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/{ticker}")
def get_ticker_info(ticker: str) -> Union[TickerInfo, list[TickerInfo]]:
    if "," in ticker:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return list(executor.map(_get_ticker_info, ticker.split(",")))

    return _get_ticker_info(ticker)


@app.get("/{ticker}/history")
def get_ticker_history(
    ticker: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> list[float]:
    yf_ticker = yf.Ticker(ticker)
    return yf_ticker.history(start=start, end=end)["Close"].tolist()


@app.exception_handler(TickerNotFoundError)
async def ticker_not_found_err_handler(
    _: Request,
    exc: TickerNotFoundError,
) -> JSONResponse:
    return JSONResponse({"message": str(exc)}, status_code=404)


@utils.cache_to_file(
    base_dir=settings.cache_dir,
    ttl=settings.cache_ttl,
    disable=settings.cache_disabled,
)
def _get_ticker_info(ticker: str) -> TickerInfo:
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.get_info()
    if info == {"trailingPegRatio": None}:
        raise TickerNotFoundError(ticker)

    price = info.get("currentPrice") or info["navPrice"]
    yearly_price_range, monthly_price_range = _get_price_range(yf_ticker)

    try:
        next_dividend_yield = round(info["lastDividendValue"] / price, 3)
    except KeyError:
        next_dividend_yield = info["trailingAnnualDividendRate"] / price

    if info.get("quoteType") == "ETF":
        earning_dates = []
    else:
        earning_dates = _get_earning_dates(yf_ticker)

    return TickerInfo(
        name=info.get("shortName", ""),
        ticker=ticker,
        price=price,
        yearly_dividend_yield=info.get("dividendYield"),
        yearly_dividend_value=info.get("dividendRate"),
        next_dividend_value=info.get("lastDividendValue"),
        next_dividend_yield=next_dividend_yield,
        currency=info["currency"],
        sector=info.get("sectorDisp", ""),
        earning_dates=earning_dates,
        website=info.get("website"),
        country=info.get("country", ""),
        industry=info.get("industryDisp", ""),
        is_etf=info.get("quoteType") == "ETF",
        ex_dividend_date=(
            datetime.date.fromtimestamp(info["exDividendDate"])  # noqa: DTZ012
            if "exDividendDate" in info
            else None
        ),
        monthly_price_range=monthly_price_range,
        yearly_price_range=yearly_price_range,
    )


def _get_earning_dates(ticker: yf.Ticker) -> list[datetime.datetime]:
    earning_dates_df = ticker.get_earnings_dates()
    return [o.to_pydatetime().date() for o in earning_dates_df.index.tolist()]


def _get_price_range(ticker: yf.Ticker) -> tuple[PriceRange, PriceRange]:
    today = datetime.datetime.now()
    one_month_ago = today - datetime.timedelta(days=30)
    one_year_ago = today - datetime.timedelta(days=365)

    # Get yearly data
    yearly_data = ticker.history(start=one_year_ago, end=today)

    # Remove timezone information from index
    yearly_data.index = yearly_data.index.tz_localize(None)

    # Filter last month from yearly data
    monthly_data = yearly_data[yearly_data.index >= one_month_ago]
    monthly_high = monthly_data["High"].max()
    monthly_low = monthly_data["Low"].min()

    # Calculate yearly highs/lows
    yearly_high = yearly_data["High"].max()
    yearly_low = yearly_data["Low"].min()

    return PriceRange(high=yearly_high, low=yearly_low), PriceRange(
        high=monthly_high, low=monthly_low
    )
