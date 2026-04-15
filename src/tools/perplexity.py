import logging
import os

import requests

logger = logging.getLogger(__name__)

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar"


def query_perplexity(prompt: str, model: str = DEFAULT_MODEL) -> str | None:
    """Send a query to Perplexity Sonar API and return the response text.

    Requires PERPLEXITY_API_KEY in environment.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        logger.warning("PERPLEXITY_API_KEY not set, skipping Perplexity query")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a financial data assistant. Provide concise, factual answers about Russian stocks (MOEX). Return data in structured format when possible."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1024,
        "temperature": 0.1,
    }

    try:
        response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        logger.warning("Perplexity API returned %d: %s", response.status_code, response.text[:200])
        return None
    except requests.RequestException as e:
        logger.warning("Perplexity request failed: %s", e)
        return None


def get_news_from_perplexity(ticker: str, limit: int = 20) -> list[dict]:
    """Fetch recent news about a Russian stock via Perplexity Sonar.

    Returns list of dicts with 'title', 'source', 'date', 'summary' keys.
    """
    prompt = (
        f"Перечисли {limit} последних важных новостей по акции {ticker} (Московская биржа). "
        "Для каждой новости укажи: дата, заголовок, источник. Формат:\n"
        "1. [ДД.ММ.ГГГГ] Заголовок — Источник\n"
    )
    text = query_perplexity(prompt)
    if not text:
        return []

    # Parse numbered list items
    news_items = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        # Remove leading number and dot/paren
        line = line.lstrip("0123456789).").strip()
        if len(line) < 10:
            continue

        # Try to extract date, title, source
        source = "Perplexity"
        title = line

        # Pattern: [DD.MM.YYYY] Title — Source
        if "]" in line:
            parts = line.split("]", 1)
            date_str = parts[0].lstrip("[")
            title = parts[1].strip()
        elif " — " in line:
            parts = line.rsplit(" — ", 1)
            title = parts[0]
            source = parts[1]

        if " — " in title:
            parts = title.rsplit(" — ", 1)
            title = parts[0]
            source = parts[1]

        news_items.append({
            "title": title[:300],
            "source": source[:100],
            "summary": "",
        })

    return news_items


def get_financial_data_from_perplexity(ticker: str) -> dict | None:
    """Fetch key financial metrics for a Russian stock via Perplexity Sonar.

    Returns dict with metric names as keys and values.
    """
    prompt = (
        f"Приведи ключевые финансовые показатели компании с тикером {ticker} (Московская биржа) "
        "за последний доступный период. Укажи:\n"
        "- Выручка (млрд руб)\n"
        "- Чистая прибыль (млрд руб)\n"
        "- EPS (руб)\n"
        "- P/E\n"
        "- P/B\n"
        "- ROE (%)\n"
        "- ROA (%)\n"
        "- Рыночная капитализация (млрд руб)\n"
        "- EV (млрд руб)\n"
        "- Дивиденд на акцию (руб)\n"
        "- Свободный денежный поток / FCF (млрд руб)\n"
        "- CAPEX (млрд руб)\n"
        "Формат: каждая строка как 'Показатель: значение'"
    )
    text = query_perplexity(prompt)
    if not text:
        return None

    # Parse key-value pairs
    result = {}
    for line in text.split("\n"):
        if ":" in line or "—" in line:
            sep = ":" if ":" in line else "—"
            parts = line.split(sep, 1)
            if len(parts) == 2:
                key = parts[0].strip().lower()
                val = parts[1].strip()
                result[key] = val

    return result if result else None
