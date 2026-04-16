import logging
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from src.data.models import CompanyNews, FinancialMetrics, LineItem

logger = logging.getLogger(__name__)

SMARTLAB_BASE = "https://smart-lab.ru"

# Mapping from Smart-Lab row names (Russian) to our field names
# Covers both bank and non-bank companies
REVENUE_PATTERNS = [
    r"Чистый операц доход",   # banks
    r"Выручка",               # non-banks
]
NET_INCOME_PATTERN = "Чистая прибыль"
EPS_PATTERN = "EPS"
CAPEX_PATTERN = "CAPEX"
FCF_PATTERN = "FCF"
OPERATING_CASH_FLOW_PATTERN = "Опер.денежный поток"
EBITDA_PATTERN = "EBITDA"
TOTAL_ASSETS_PATTERN = "Активы"
TOTAL_LIABILITIES_PATTERN = "Обязательства"
CAPITAL_PATTERN = "Капитал"
SHARES_PATTERN = "Число акций ао"
DIVIDEND_PER_SHARE_PATTERN = "Дивиденд,руб/акцию"
MARKET_CAP_PATTERN = "Капитализация"
EV_PATTERN = "EV"
PE_PATTERN = "P/E"
PB_PATTERN = "P/B"
ROE_PATTERN = "ROE"
ROA_PATTERN = "ROA"
OPERATING_MARGIN_PATTERN = "Рентабельность"  # Рентабельность банка / Рентабельность по EBITDA
NET_MARGIN_PATTERN = "Чистая процентная маржа"
DEBT_PATTERN = "Чистый долг"


def _parse_number(value: str) -> float | None:
    """Parse a number from Smart-Lab format (e.g. '2 501', '12.5%', '-517.2')."""
    if not value or value in ("?", "-", "", "—"):
        return None
    # Remove spaces, %, and replace comma with dot
    cleaned = value.replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    # Remove trailing %
    cleaned = cleaned.rstrip("%")
    # Handle negative in parentheses or with minus
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_billion(value: str) -> float | None:
    """Parse a value in billions from Smart-Lab and return absolute value."""
    num = _parse_number(value)
    if num is not None:
        return num * 1e9  # billions to absolute
    return None


def _get_row_value(rows_dict: dict, patterns: list[str] | str, col_index: int) -> str | None:
    """Find a row by pattern(s) and return the value at col_index."""
    if isinstance(patterns, str):
        patterns = [patterns]
    for row_name, values in rows_dict.items():
        for pattern in patterns:
            if re.search(pattern, row_name, re.IGNORECASE):
                if col_index < len(values):
                    return values[col_index]
    return None


def _fix_mojibake(text: str) -> str:
    """Fix mojibake from Smart-Lab: cp1251 bytes decoded as utf-8."""
    try:
        return text.encode("cp1251").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def fetch_financial_table(ticker: str, period: str = "y") -> dict[str, list[str]] | None:
    """Fetch and parse the MSFO financial table from Smart-Lab.

    Args:
        ticker: Stock ticker (e.g. 'SBER', 'GAZP')
        period: 'y' for yearly, 'q' for quarterly

    Returns:
        Dictionary mapping row names to list of values (by year/quarter)
    """
    url = f"{SMARTLAB_BASE}/q/{ticker}/f/{period}/"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if r.status_code != 200:
            logger.warning("Smart-Lab returned %d for %s", r.status_code, ticker)
            return None
    except requests.RequestException as e:
        logger.warning("Smart-Lab request failed for %s: %s", ticker, e)
        return None

    # Smart-Lab serves pages in windows-1251 but declares utf-8.
    # Parse raw bytes with lxml, then fix mojibake in text.
    soup = BeautifulSoup(r.content, "lxml")
    table = soup.find("table")
    if not table:
        logger.warning("No financial table found for %s", ticker)
        return None

    rows_dict = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        texts = [_fix_mojibake(c.get_text(strip=True)) for c in cells]
        if len(texts) >= 3 and texts[0]:
            row_name = texts[0]
            # Skip header rows and empty name rows
            if row_name and not row_name.startswith(tuple("0123456789")):
                # Remove 'smart-lab.ru' suffix from company name
                row_name = row_name.replace("smart-lab.ru", "").strip()
                values = texts[1:]  # skip the name column
                rows_dict[row_name] = values

    return rows_dict


def get_financial_metrics_from_smartlab(
    ticker: str,
    end_date: str,
    period: str = "annual",
) -> list[FinancialMetrics] | None:
    """Fetch financial metrics from Smart-Lab MSFO table."""
    sl_period = "y" if period in ("annual", "ttm") else "q"
    rows = fetch_financial_table(ticker, sl_period)
    if not rows:
        return None

    # Determine column index for most recent data
    # Find the year header row to know column layout
    # Typically: ['', '?', '', '2021', '2022', '2023', '2024', '2025', '', 'LTM?']
    # We want the last non-empty year column
    # For simplicity, try column index 5 (usually latest full year) or find LTM

    # Try LTM column first (usually last), then latest year
    # Column structure varies, so we search from the end
    def get_val(patterns):
        val = _get_row_value(rows, patterns, -1)  # try last column (often LTM)
        if val is None or val in ("?", "", "-"):
            # Try second to last
            val = _get_row_value(rows, patterns, -2)
        return val

    def get_billion(patterns):
        raw = get_val(patterns)
        return _parse_billion(raw) if raw else None

    def get_float(patterns):
        raw = get_val(patterns)
        return _parse_number(raw) if raw else None

    def get_pct(patterns):
        raw = get_val(patterns)
        num = _parse_number(raw)
        return num / 100.0 if num is not None else None

    metrics = FinancialMetrics(
        ticker=ticker,
        report_period=end_date,
        period=period,
        currency="RUB",
        market_cap=get_billion([MARKET_CAP_PATTERN]),
        enterprise_value=get_billion([EV_PATTERN]),
        price_to_earnings_ratio=get_float([PE_PATTERN]),
        price_to_book_ratio=get_float([PB_PATTERN]),
        price_to_sales_ratio=None,
        enterprise_value_to_ebitda_ratio=None,
        enterprise_value_to_revenue_ratio=None,
        free_cash_flow_yield=None,
        peg_ratio=None,
        gross_margin=None,
        operating_margin=get_pct([OPERATING_MARGIN_PATTERN]),
        net_margin=get_pct([NET_MARGIN_PATTERN]),
        return_on_equity=get_pct([ROE_PATTERN]),
        return_on_assets=get_pct([ROA_PATTERN]),
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
        earnings_per_share=get_float([EPS_PATTERN]),
        book_value_per_share=None,
        free_cash_flow_per_share=None,
    )

    return [metrics]


def get_line_items_from_smartlab(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "annual",
    limit: int = 10,
) -> list[LineItem]:
    """Fetch financial line items from Smart-Lab MSFO table.

    Maps requested line item names to Smart-Lab Russian row names.
    """
    sl_period = "y" if period in ("annual", "ttm") else "q"
    rows = fetch_financial_table(ticker, sl_period)
    if not rows:
        return []

    # Map requested line items to Smart-Lab patterns
    item_patterns = {
        "revenue": REVENUE_PATTERNS,
        "net_income": [NET_INCOME_PATTERN],
        "earnings_per_share": [EPS_PATTERN],
        "free_cash_flow": [FCF_PATTERN, OPERATING_CASH_FLOW_PATTERN],
        "capital_expenditure": [CAPEX_PATTERN],
        "operating_income": ["Операционная прибыль", "Опер. прибыль"],
        "total_assets": ["Активы"],
        "total_liabilities": ["Обязательства", "Кредитный портфель"],
        "current_assets": ["Наличность"],
        "current_liabilities": ["Депозиты"],
        "book_value_per_share": [CAPITAL_PATTERN, SHARES_PATTERN],
        "outstanding_shares": [SHARES_PATTERN],
        "dividends_and_other_cash_distributions": [DIVIDEND_PER_SHARE_PATTERN],
        "depreciation_and_amortization": ["Амортизация"],
        "ebitda": [EBITDA_PATTERN],
        "operating_cash_flow": [OPERATING_CASH_FLOW_PATTERN],
        "shareholders_equity": [CAPITAL_PATTERN],
        "ebit": ["EBIT"],
        "total_debt": [DEBT_PATTERN],
    }

    # Collect data for the latest column
    item_values = {}
    for requested_item in line_items:
        patterns = item_patterns.get(requested_item, [requested_item])
        raw_val = _get_row_value(rows, patterns, -1)
        if raw_val and raw_val not in ("?", "-", ""):
            parsed = _parse_number(raw_val)
            if parsed is not None:
                # Smart-Lab values are in billions, store as-is for now
                # The LLM agents will interpret the numbers
                item_values[requested_item] = parsed * 1e9  # convert from billions

    if not item_values:
        return []

    item = LineItem(
        ticker=ticker,
        report_period=end_date,
        period=period,
        currency="RUB",
        **item_values,
    )

    return [item]


def get_news_from_smartlab(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 50,
) -> list[CompanyNews]:
    """Fetch company news from Smart-Lab news forum.

    Parses the news page at smart-lab.ru/forum/news/{TICKER}/
    """
    url = f"{SMARTLAB_BASE}/forum/news/{ticker}/"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.encoding = "utf-8"
        if r.status_code != 200:
            logger.warning("Smart-Lab news returned %d for %s", r.status_code, ticker)
            return []
    except requests.RequestException as e:
        logger.warning("Smart-Lab news request failed for %s: %s", ticker, e)
        return []

    soup = BeautifulSoup(r.text, "lxml")

    # Find blog post links which are the news items
    news_items = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)
        # News are blog posts linked from the news page
        if "/blog/" in href and len(text) > 30:
            # Try to extract source from the text (often at the end after "—")
            source = "Smart-Lab"
            title = text
            if " — " in text:
                parts = text.rsplit(" — ", 1)
                title = parts[0]
                source = parts[1]

            # Build full URL
            if href.startswith("/"):
                full_url = SMARTLAB_BASE + href
            else:
                full_url = href

            news_items.append(CompanyNews(
                ticker=ticker,
                title=title[:300],
                source=source[:100],
                date=end_date,  # Smart-Lab doesn't show exact dates easily
                url=full_url,
            ))

            if len(news_items) >= limit:
                break

    return news_items
