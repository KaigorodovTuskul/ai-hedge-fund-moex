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
from src.tools.smartlab import (
    get_financial_metrics_from_smartlab,
    get_line_items_from_smartlab,
    get_news_from_smartlab,
)
from src.tools.marketcap import (
    get_financial_metrics_from_marketcap,
    get_line_items_from_marketcap,
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
    """Fetch financial metrics from Smart-Lab (primary) + MOEX (fallback)."""
    cache_key = f"{ticker}_{period}_{end_date}_{limit}"

    if cached_data := _cache.get_financial_metrics(cache_key):
        return [FinancialMetrics(**metric) for metric in cached_data]

    # Primary: Smart-Lab MSFO data
    sl_period = "annual" if period in ("annual", "ttm") else "quarterly"
    metrics = get_financial_metrics_from_smartlab(ticker, end_date, sl_period)

    if not metrics:
        # Fallback: basic metrics from MOEX market data
        market_data = _get_market_data(ticker)
        market_cap = market_data["market_cap"] if market_data else None

        metrics = [FinancialMetrics(
            ticker=ticker,
            report_period=end_date,
            period=period,
            currency="RUB",
            market_cap=float(market_cap) if market_cap else None,
        )]

    # Fill gaps from marketcap.ru
    mc_metrics = get_financial_metrics_from_marketcap(ticker, end_date, sl_period)
    if mc_metrics:
        mc = mc_metrics[0]
        base = metrics[0]
        updated = base.model_dump()
        for field_name, field_value in mc.model_dump().items():
            if field_name in ("ticker", "report_period", "period", "currency"):
                continue
            # Only fill gaps (None values)
            if updated.get(field_name) is None and field_value is not None:
                updated[field_name] = field_value
        metrics = [FinancialMetrics(**updated)]

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
    """Fetch financial line items from Smart-Lab, fallback to marketcap.ru for missing items."""
    sl_period = "annual" if period in ("annual", "ttm") else "quarterly"
    items = get_line_items_from_smartlab(ticker, line_items, end_date, sl_period, limit)

    # Determine which items are still missing
    if items:
        found_fields = set(k for k, v in items[0].__pydantic_extra__.items() if v is not None) if items[0].__pydantic_extra__ else set()
    else:
        found_fields = set()
    missing_items = [it for it in line_items if it not in found_fields]

    if missing_items:
        mc_items = get_line_items_from_marketcap(ticker, missing_items, end_date, sl_period, limit)
        if mc_items and mc_items[0].__pydantic_extra__:
            if items:
                # Merge into existing item
                merged = items[0].__pydantic_extra__.copy()
                merged.update({k: v for k, v in mc_items[0].__pydantic_extra__.items() if v is not None})
                items = [LineItem(
                    ticker=ticker,
                    report_period=items[0].report_period,
                    period=items[0].period,
                    currency=items[0].currency,
                    **merged,
                )]
            else:
                items = mc_items

    return items


def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    """Not available for Russian market. Returns empty list."""
    return []


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[CompanyNews]:
    """Fetch company news from Smart-Lab news forum."""
    return get_news_from_smartlab(ticker, end_date, start_date, limit)


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
