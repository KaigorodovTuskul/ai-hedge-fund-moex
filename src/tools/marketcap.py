"""Scraper for marketcap.ru — fallback financial data source for MOEX stocks.

Provides income statement, balance sheet, cash flow, financial ratios,
and dividend data that may be missing from Smart-Lab.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from src.data.models import FinancialMetrics, LineItem

logger = logging.getLogger(__name__)

MARKETCAP_BASE = "https://marketcap.ru"

# Cache directory for disk persistence
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "marketcap"
_CACHE_TTL = 86400  # 24 hours


# ── Number parsing ──────────────────────────────────────────────────────────

_SUFFIX_MULTIPLIERS = {
    "трлн": 1e12,
    "млрд": 1e9,
    "млн": 1e6,
    "тыс": 1e3,
    "т": 1e12,
    "б": 1e9,
    "м": 1e6,
}


def _parse_russian_number(value: str) -> float | None:
    """Parse Russian-formatted numbers: '5.68 трлн', '820 млрд', '3.86', '-1.52 трлн'."""
    if not value or value.strip() in ("", "-", "—", "?"):
        return None
    value = value.strip().replace("\xa0", " ").replace(",", ".")
    # Remove currency symbol
    value = value.replace("₽", "").replace("$", "").replace("€", "").strip()

    # Try "number suffix" pattern (e.g. "5.68 трлн", "820 млрд")
    m = re.match(r"^([+-]?\d[\d\s.]*?)\s*(трлн|млрд|млн|тыс)\.?$", value, re.I)
    if m:
        num_str = m.group(1).replace(" ", "")
        suffix = m.group(2).lower()
        try:
            return float(num_str) * _SUFFIX_MULTIPLIERS[suffix]
        except ValueError:
            return None

    # Plain number
    try:
        return float(value.replace(" ", ""))
    except ValueError:
        return None


# ── HTML table fetching & parsing ───────────────────────────────────────────

def _cache_path(ticker: str, page_type: str) -> Path:
    return _CACHE_DIR / f"{ticker}_{page_type}.json"


def _read_disk_cache(ticker: str, page_type: str) -> dict | None:
    path = _cache_path(ticker, page_type)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_timestamp", 0) < _CACHE_TTL:
            return data.get("rows")
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _write_disk_cache(ticker: str, page_type: str, rows: dict):
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(ticker, page_type)
    try:
        path.write_text(
            json.dumps({"_timestamp": time.time(), "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("Failed to write cache for %s/%s: %s", ticker, page_type, e)


def fetch_table(ticker: str, page_type: str) -> dict[str, dict[str, float | None]] | None:
    """Fetch and parse an HTML table from marketcap.ru.

    Args:
        ticker: e.g. 'SBER'
        page_type: one of 'income', 'balance', 'cash-flow', 'ratios', 'dividends'

    Returns:
        {metric_name: {year: value}}  (years as strings, most recent first)
        None on failure.
    """
    # Check disk cache first
    cached = _read_disk_cache(ticker, page_type)
    if cached is not None:
        return cached

    url_map = {
        "income": f"/stocks/{ticker}/financial-statements/income-statement",
        "balance": f"/stocks/{ticker}/financial-statements/balance-sheet",
        "cash-flow": f"/stocks/{ticker}/financial-statements/cash-flow",
        "ratios": f"/stocks/{ticker}/financial-ratios",
        "dividends": f"/stocks/{ticker}/dividends",
    }
    url = MARKETCAP_BASE + url_map.get(page_type, "")
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if r.status_code != 200:
            logger.warning("marketcap.ru returned %d for %s", r.status_code, url)
            return None
    except requests.RequestException as e:
        logger.warning("marketcap.ru request failed: %s", e)
        return None

    soup = BeautifulSoup(r.text, "lxml")
    table = soup.find("table", class_=re.compile(r"table.*table-detail-stocks"))
    if not table:
        logger.warning("No table found for %s/%s", ticker, page_type)
        return None

    # Parse header row → year list
    header_row = table.find("thead")
    years: list[str] = []
    if header_row:
        for th in header_row.find_all("th"):
            txt = th.get_text(strip=True)
            if re.match(r"^\d{4}$", txt):
                years.append(txt)

    # Parse data rows
    result: dict[str, dict[str, float | None]] = {}
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        # Metric name from the title attribute or cell text
        title_span = tds[0].find("span", attrs={"title": True})
        if title_span:
            metric_name = title_span.get("title", "").strip()
        else:
            metric_name = tds[0].get_text(strip=True)

        if not metric_name:
            continue

        # Values — skip first td (name), rest are year columns
        values_td = tds[1:]
        year_values: dict[str, float | None] = {}
        for i, td in enumerate(values_td):
            if i < len(years):
                val = _parse_russian_number(td.get_text(strip=True))
                year_values[years[i]] = val

        result[metric_name] = year_values

    if result:
        _write_disk_cache(ticker, page_type, result)
    return result


# ── Metric name mappings ────────────────────────────────────────────────────

# Maps FinancialMetrics field → list of Russian titles from marketcap.ru
_RATIOS_MAP = {
    "price_to_earnings_ratio": ["Цена/Прибыль, P/E"],
    "price_to_book_ratio": ["Цена/Балансовая стоимость, P/B"],
    "price_to_sales_ratio": ["Цена/Выручка, P/S"],
    "peg_ratio": ["Цена/Прибыль/Рост, PEG"],
    "gross_margin": ["Валовая рентабельность"],
    "operating_margin": ["Операционная маржа"],
    "net_margin": ["Чистая рентабельность продаж"],
    "return_on_equity": ["Рентабельность собственного капитала, ROE"],
    "return_on_assets": ["Рентабельность активов, ROA"],
    "current_ratio": ["Текущая ликвидность"],
    "quick_ratio": ["Быстрая ликвидность"],
    "debt_to_equity": ["Задолженность/Капитал"],
    "interest_coverage": ["Покрытие процентов"],
    "payout_ratio": ["Доля от прибыли для выплаты дивидендов"],
    "free_cash_flow_per_share": ["Объем свободного денежного потока на акцию"],
    "operating_cash_flow_ratio": ["Операционный денежный поток/Выручка"],
    "asset_turnover": ["Оборот активов"],
    "inventory_turnover": ["Оборот запасов"],
    "receivables_turnover": ["Оборот дебиторской задолженности"],
    "effective_tax_rate": ["Эффективная налоговая ставка"],
}

# Maps line item field → Russian titles
_INCOME_MAP = {
    "revenue": ["Выручка"],
    "cost_of_revenue": ["Себестоимость выручки"],
    "gross_profit": ["Валовая прибыль"],
    "operating_income": ["Операционная прибыль"],
    "ebit": ["Операционная прибыль"],
    "interest_expense": ["Процентные расходы"],
    "ebitda": ["EBITDA"],
    "depreciation_and_amortization": ["Износ и амортизация"],
    "earnings_per_share": ["Прибыль на акцию, EPS"],
    "operating_expenses": ["Операционные расходы"],
}

_BALANCE_MAP = {
    "cash_and_equivalents": ["Денежные средства и их эквиваленты"],
    "total_current_assets": ["Общие текущие активы"],
    "total_assets": ["Общие активы"],
    "total_current_liabilities": ["Общие текущие обязательства"],
    "total_liabilities": ["Общие обязательства"],
    "shareholders_equity": ["Общий акционерный капитал"],
    "total_debt": ["Общая задолженность"],
    "net_debt": ["Чистый долг"],
    "long_term_debt": ["Долгосрочный долг"],
    "short_term_debt": ["Краткосрочный долг"],
    "outstanding_shares": ["Количество акций"],
}

_CASHFLOW_MAP = {
    "free_cash_flow": ["Свободный денежный поток"],
    "capital_expenditure": ["Капитальные расходы"],
    "operating_cash_flow": ["Денежные потоки от операционной деятельности"],
    "net_income": ["Чистая прибыль"],
    "dividends_paid": ["Выплаченные дивиденды"],
}


def _get_latest(data: dict[str, float | None] | None) -> float | None:
    """Get the most recent non-None value from a {year: value} dict."""
    if not data:
        return None
    for year in sorted(data.keys(), reverse=True):
        if data[year] is not None:
            return data[year]
    return None


def _get_latest_ratio(data: dict[str, float | None] | None) -> float | None:
    """Get the most recent value from ratio data. Ratios are already 0-1 or plain numbers."""
    return _get_latest(data)


# ── Public API ──────────────────────────────────────────────────────────────

def get_financial_metrics_from_marketcap(
    ticker: str,
    end_date: str,
    period: str = "annual",
) -> list[FinancialMetrics] | None:
    """Fetch financial ratios from marketcap.ru to fill gaps from Smart-Lab."""
    ratios_table = fetch_table(ticker, "ratios")
    if not ratios_table:
        return None

    # Build metric lookup: {field_name: latest_value}
    values: dict[str, float | None] = {}
    for field, titles in _RATIOS_MAP.items():
        for title in titles:
            if title in ratios_table:
                val = _get_latest_ratio(ratios_table[title])
                if val is not None:
                    # Ratios on marketcap.ru may be expressed as percentages (e.g. 54 for 54%)
                    # or as decimals (e.g. 0.54). We detect: if val > 1 for margin-like fields, divide by 100.
                    if field in ("gross_margin", "operating_margin", "net_margin",
                                 "payout_ratio", "effective_tax_rate",
                                 "operating_cash_flow_ratio") and val > 1:
                        val = val / 100.0
                    values[field] = val
                break

    if not values:
        return None

    # Determine report period from the most recent year available
    report_year = end_date[:4]
    for title_data in ratios_table.values():
        for yr in sorted(title_data.keys(), reverse=True):
            if title_data[yr] is not None:
                report_year = yr
                break
        break

    metrics = FinancialMetrics(
        ticker=ticker,
        report_period=f"{report_year}-12-31",
        period=period,
        currency="RUB",
        # Valuation
        market_cap=None,
        enterprise_value=None,
        price_to_earnings_ratio=values.get("price_to_earnings_ratio"),
        price_to_book_ratio=values.get("price_to_book_ratio"),
        price_to_sales_ratio=values.get("price_to_sales_ratio"),
        enterprise_value_to_ebitda_ratio=None,
        enterprise_value_to_revenue_ratio=None,
        free_cash_flow_yield=None,
        peg_ratio=values.get("peg_ratio"),
        # Profitability
        gross_margin=values.get("gross_margin"),
        operating_margin=values.get("operating_margin"),
        net_margin=values.get("net_margin"),
        return_on_equity=values.get("return_on_equity"),
        return_on_assets=values.get("return_on_assets"),
        return_on_invested_capital=None,
        # Efficiency
        asset_turnover=values.get("asset_turnover"),
        inventory_turnover=values.get("inventory_turnover"),
        receivables_turnover=values.get("receivables_turnover"),
        days_sales_outstanding=None,
        operating_cycle=None,
        working_capital_turnover=None,
        # Liquidity
        current_ratio=values.get("current_ratio"),
        quick_ratio=values.get("quick_ratio"),
        cash_ratio=None,
        operating_cash_flow_ratio=values.get("operating_cash_flow_ratio"),
        # Debt
        debt_to_equity=values.get("debt_to_equity"),
        debt_to_assets=None,
        interest_coverage=values.get("interest_coverage"),
        # Growth
        revenue_growth=None,
        earnings_growth=None,
        book_value_growth=None,
        earnings_per_share_growth=None,
        free_cash_flow_growth=None,
        operating_income_growth=None,
        ebitda_growth=None,
        # Per share
        payout_ratio=values.get("payout_ratio"),
        earnings_per_share=None,
        book_value_per_share=None,
        free_cash_flow_per_share=values.get("free_cash_flow_per_share"),
    )
    return [metrics]


def get_line_items_from_marketcap(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "annual",
    limit: int = 10,
) -> list[LineItem]:
    """Fetch financial line items from marketcap.ru.

    Tries income statement, balance sheet, and cash flow tables.
    Returns items that Smart-Lab couldn't provide.
    """
    all_maps = {**_INCOME_MAP, **_BALANCE_MAP, **_CASHFLOW_MAP}
    # Determine which tables we need to fetch
    needed_tables: set[str] = set()
    for item in line_items:
        for field, _ in _INCOME_MAP.items():
            if field == item:
                needed_tables.add("income")
        for field, _ in _BALANCE_MAP.items():
            if field == item:
                needed_tables.add("balance")
        for field, _ in _CASHFLOW_MAP.items():
            if field == item:
                needed_tables.add("cash-flow")

    tables: dict[str, dict] = {}
    for table_type in needed_tables:
        t = fetch_table(ticker, table_type)
        if t:
            tables[table_type] = t

    if not tables:
        return []

    # Collect values
    item_values: dict[str, float] = {}
    for requested_item in line_items:
        # Find which table has this item
        for field, titles in all_maps.items():
            if field != requested_item:
                continue
            for title in titles:
                for table_data in tables.values():
                    if title in table_data:
                        val = _get_latest(table_data[title])
                        if val is not None:
                            item_values[requested_item] = val
                            break
                if requested_item in item_values:
                    break

    if not item_values:
        return []

    # Determine report period from data
    report_year = end_date[:4]
    for table_data in tables.values():
        for metric_data in table_data.values():
            for yr in sorted(metric_data.keys(), reverse=True):
                if metric_data[yr] is not None:
                    report_year = yr
                    break
            break
        break

    item = LineItem(
        ticker=ticker,
        report_period=f"{report_year}-12-31",
        period=period,
        currency="RUB",
        **item_values,
    )
    return [item]
