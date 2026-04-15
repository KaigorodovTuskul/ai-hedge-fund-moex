import datetime
import logging
import pandas as pd
import requests
import time

logger = logging.getLogger(__name__)

from src.data.cache import get_cache
from src.data.models import (
    CompanyNews,
    FinancialMetrics,
    Price,
    LineItem,
    InsiderTrade,
)

# Global cache instance
_cache = get_cache()

# MOEX ISS API constants
MOEX_BASE_URL = "https://iss.moex.com/iss"
MOEX_BOARD = "TQBR"  # Main board for Russian shares (T+)


def _make_moex_request(url: str, max_retries: int = 3) -> dict | None:
    """Make a request to MOEX ISS API with basic retry logic."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429 and attempt < max_retries - 1:
                delay = 5 * (attempt + 1)
                logger.warning("MOEX rate limited. Waiting %ds...", delay)
                time.sleep(delay)
                continue
            logger.warning("MOEX API returned status %d for %s", response.status_code, url)
            return None
        except requests.RequestException as e:
            logger.warning("MOEX request failed (attempt %d): %s", attempt + 1, e)
            if attempt < max_retries - 1:
                time.sleep(2)
    return None


def get_prices(ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
    """Fetch daily price data from MOEX ISS API."""
    cache_key = f"{ticker}_{start_date}_{end_date}"

    if cached_data := _cache.get_prices(cache_key):
        return [Price(**price) for price in cached_data]

    url = (
        f"{MOEX_BASE_URL}/engines/stock/markets/shares/boards/{MOEX_BOARD}"
        f"/securities/{ticker}/candles.json"
        f"?from={start_date}&till={end_date}&interval=24&iss.meta=off"
    )
    data = _make_moex_request(url)
    if not data:
        return []

    try:
        candles = data.get("candles", {})
        columns = candles.get("columns", [])
        rows = candles.get("data", [])

        if not rows:
            return []

        col_map = {col: i for i, col in enumerate(columns)}
        prices = []
        for row in rows:
            prices.append(Price(
                open=float(row[col_map["open"]]),
                close=float(row[col_map["close"]]),
                high=float(row[col_map["high"]]),
                low=float(row[col_map["low"]]),
                volume=int(row[col_map["volume"]]),
                time=str(row[col_map["begin"]]).split(" ")[0],
            ))
    except Exception as e:
        logger.warning("Failed to parse MOEX candles for %s: %s", ticker, e)
        return []

    if not prices:
        return []

    _cache.set_prices(cache_key, [p.model_dump() for p in prices])
    return prices


def _get_securities_info(ticker: str) -> dict | None:
    """Fetch security info from MOEX (issue size, short name, etc.)."""
    cache_key = f"moex_securities_{ticker}"

    if cached := _cache.get_financial_metrics(cache_key):
        return cached

    url = (
        f"{MOEX_BASE_URL}/engines/stock/markets/shares/boards/{MOEX_BOARD}"
        f"/securities.json?iss.meta=off&iss.only=securities"
        f"&securities.columns=SECID,SHORTNAME,ISSUESIZE,PREVPRICE"
    )
    data = _make_moex_request(url)
    if not data:
        return None

    columns = data["securities"]["columns"]
    col_map = {col: i for i, col in enumerate(columns)}

    for row in data["securities"]["data"]:
        if row[col_map["SECID"]] == ticker:
            result = {
                "ticker": ticker,
                "shortname": row[col_map.get("SHORTNAME", -1)] if "SHORTNAME" in col_map else None,
                "issue_size": row[col_map.get("ISSUESIZE", -1)] if "ISSUESIZE" in col_map else None,
                "prev_price": row[col_map.get("PREVPRICE", -1)] if "PREVPRICE" in col_map else None,
            }
            _cache.set_financial_metrics(cache_key, result)
            return result
    return None


def _get_market_data(ticker: str) -> dict | None:
    """Fetch real-time market data from MOEX (market cap, last price, etc.)."""
    url = (
        f"{MOEX_BASE_URL}/engines/stock/markets/shares/boards/{MOEX_BOARD}"
        f"/securities.json?iss.meta=off&iss.only=marketdata"
        f"&marketdata.columns=SECID,ISSUECAPITALIZATION,LAST,MARKETPRICE"
    )
    data = _make_moex_request(url)
    if not data:
        return None

    columns = data["marketdata"]["columns"]
    col_map = {col: i for i, col in enumerate(columns)}

    for row in data["marketdata"]["data"]:
        if row[col_map["SECID"]] == ticker:
            return {
                "market_cap": row[col_map.get("ISSUECAPITALIZATION", -1)],
                "last": row[col_map.get("LAST", -1)],
                "market_price": row[col_map.get("MARKETPRICE", -1)],
            }
    return None


def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[FinancialMetrics]:
    """Fetch financial metrics from MOEX.

    Note: MOEX ISS API provides limited fundamental data without authentication.
    We return market cap and price-based metrics from available market data.
    """
    cache_key = f"{ticker}_{period}_{end_date}_{limit}"

    if cached_data := _cache.get_financial_metrics(cache_key):
        return [FinancialMetrics(**metric) for metric in cached_data]

    market_data = _get_market_data(ticker)
    market_cap = market_data["market_cap"] if market_data else None

    metrics = [FinancialMetrics(
        ticker=ticker,
        report_period=end_date,
        period=period,
        currency="RUB",
        market_cap=float(market_cap) if market_cap else None,
        enterprise_value=None,
        price_to_earnings_ratio=None,
        price_to_book_ratio=None,
        price_to_sales_ratio=None,
        enterprise_value_to_ebitda_ratio=None,
        enterprise_value_to_revenue_ratio=None,
        free_cash_flow_yield=None,
        peg_ratio=None,
        gross_margin=None,
        operating_margin=None,
        net_margin=None,
        return_on_equity=None,
        return_on_assets=None,
        return_on_invested_capital=None,
        asset_turnover=None,
        inventory_turnover=None,
        receivables_turnover=None,
        days_sales_outstanding=None,
        operating_cycle=None,
        working_capital_turnover=None,
        current_ratio=None,
        quick_ratio=None,
        cash_ratio=None,
        operating_cash_flow_ratio=None,
        debt_to_equity=None,
        debt_to_assets=None,
        interest_coverage=None,
        revenue_growth=None,
        earnings_growth=None,
        book_value_growth=None,
        earnings_per_share_growth=None,
        free_cash_flow_growth=None,
        operating_income_growth=None,
        ebitda_growth=None,
        payout_ratio=None,
        earnings_per_share=None,
        book_value_per_share=None,
        free_cash_flow_per_share=None,
    )]

    _cache.set_financial_metrics(cache_key, [m.model_dump() for m in metrics])
    return metrics


def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[LineItem]:
    """Not available via MOEX ISS API without authentication."""
    return []


def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    """Not available via MOEX ISS API."""
    return []


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[CompanyNews]:
    """Not available via MOEX ISS API."""
    return []


def get_market_cap(
    ticker: str,
    end_date: str,
    api_key: str = None,
) -> float | None:
    """Fetch market cap from MOEX market data."""
    market_data = _get_market_data(ticker)
    if market_data and market_data.get("market_cap"):
        return float(market_data["market_cap"])

    financial_metrics = get_financial_metrics(ticker, end_date, api_key=api_key)
    if financial_metrics and financial_metrics[0].market_cap:
        return float(financial_metrics[0].market_cap)

    return None


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert prices to a DataFrame."""
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    numeric_cols = ["open", "close", "high", "low", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


def get_price_data(ticker: str, start_date: str, end_date: str, api_key: str = None) -> pd.DataFrame:
    prices = get_prices(ticker, start_date, end_date, api_key=api_key)
    return prices_to_df(prices)
