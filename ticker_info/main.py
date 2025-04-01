import concurrent.futures
import datetime
import enum
from itertools import repeat
import pandas as pd
from typing import Literal, Optional, Union

import pydantic
import pydantic_settings
import yfinance as yf  # type: ignore
from fastapi import FastAPI, HTTPException
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


class HistoricalEntry(pydantic.BaseModel):
    date: datetime.date
    price: float


class TickerInfo(pydantic.BaseModel):
    price: float
    change_rate: float
    name: str
    ticker: str
    yearly_dividend_yield: Optional[float]
    next_dividend_yield: float
    yearly_dividend_value: Optional[float]
    next_dividend_value: Optional[float]
    website: Optional[str]
    currency: Literal["EUR", "USD", "GBp"]
    ex_dividend_date: Optional[datetime.date]
    dividend_payment_date: Optional[datetime.date]
    earning_dates: list[datetime.datetime]
    sector: str
    country: str
    industry: str
    is_etf: bool
    monthly_price_range: PriceRange
    yearly_price_range: PriceRange
    historical_data: list[HistoricalEntry] = []


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


class HistoryResample(str, enum.Enum):
    month = "month"
    year = "year"
    day = "day"


@app.get("/{ticker}")
def get_ticker_info(
    ticker: str,
    history_resample: Optional[HistoryResample] = None,
    history_start: Optional[datetime.datetime] = None,
    history_end: Optional[datetime.datetime] = None,
) -> Union[TickerInfo, list[TickerInfo]]:
    history_end = history_end or datetime.datetime.now()

    is_any_provided = history_resample is not None or history_start is not None
    is_any_none = history_resample is None or history_start is None
    if is_any_none and is_any_provided:
        raise HTTPException(
            status_code=400,
            detail="If any of history_resample, history_start, or history_end is provided, all must be provided",
        )

    if "," in ticker:
        tickers = ticker.split(",")
        it = zip(
            tickers,
            repeat(history_resample),
            repeat(history_start),
            repeat(history_end),
        )
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return list(executor.map(lambda x: _get_ticker_info(*x), it))

    return _get_ticker_info(
        ticker, history_resample, history_start, history_end
    )


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
def _get_ticker_info(
    ticker: str,
    history_resample: Optional[HistoryResample] = None,
    history_start: Optional[datetime.datetime] = None,
    history_end: Optional[datetime.datetime] = None,
) -> TickerInfo:
    yf_ticker = yf.Ticker(ticker)
    try:
        info = yf_ticker.get_info()
    except AttributeError:
        raise TickerNotFoundError(ticker)

    if info == {"trailingPegRatio": None}:
        raise TickerNotFoundError(ticker)

    price = info.get("currentPrice") or info["navPrice"]
    change_rate = (price - info["previousClose"]) / info["previousClose"] * 100
    calendar = yf_ticker.get_calendar()
    payment_date = calendar.get("Dividend Date")
    yearly_price_range, monthly_price_range = _get_price_range(yf_ticker)

    try:
        next_dividend_yield = round(info["lastDividendValue"] / price, 3)
    except KeyError:
        next_dividend_yield = round(
            info["trailingAnnualDividendRate"] / price, 3
        )

    yearly_dividend_yield = round(
        info["trailingAnnualDividendYield"] / price, 3
    )

    if info.get("quoteType") == "ETF":
        earning_dates = []
    else:
        earning_dates = _get_earning_dates(yf_ticker)

    if (
        history_resample is not None
        and history_start is not None
        and history_end is not None
    ):
        historical_data = _get_historical_data(
            yf_ticker, history_resample, history_start, history_end
        )
    else:
        historical_data = []

    return TickerInfo(
        name=info.get("shortName", ""),
        ticker=ticker,
        price=price,
        change_rate=change_rate,
        yearly_dividend_yield=yearly_dividend_yield,
        yearly_dividend_value=info.get("trailingAnnualDividendRate"),
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
        dividend_payment_date=payment_date,
        monthly_price_range=monthly_price_range,
        yearly_price_range=yearly_price_range,
        historical_data=historical_data,
    )


def _get_earning_dates(ticker: yf.Ticker) -> list[datetime.datetime]:
    earning_dates_df = ticker.get_earnings_dates()
    if isinstance(earning_dates_df.index, pd.DatetimeIndex):
        return [o.to_pydatetime().date() for o in earning_dates_df.index]
    else:
        return []


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


def _get_historical_data(
    ticker: yf.Ticker,
    resample: HistoryResample,
    start: datetime.datetime,
    end: datetime.datetime,
) -> list[HistoricalEntry]:
    data = ticker.history(start=start, end=end)
    if resample == HistoryResample.month:
        return [
            HistoricalEntry(date=date, price=price)
            for date, price in data["Close"].resample("MS").first().items()
        ]
    elif resample == HistoryResample.year:
        return [
            HistoricalEntry(date=date, price=price)
            for date, price in data["Close"].resample("YS").first().items()
        ]
    elif resample == HistoryResample.day:
        return [
            HistoricalEntry(date=date, price=price)
            for date, price in data["Close"].items()
        ]
