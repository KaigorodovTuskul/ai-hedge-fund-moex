"""Streamlit GUI for AI Hedge Fund (MOEX)."""

import sys
import os
import json
import traceback

# Add project root to path
sys.path.insert(0, os.path.dirname(os_file__ := os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from src.tools.api import get_prices, get_financial_metrics, get_market_cap
from src.utils.analysts import ANALYST_ORDER
from src.main import run_hedge_fund
from src.llm.models import LLM_ORDER, ModelProvider

st.set_page_config(page_title="AI Hedge Fund — MOEX", page_icon="📈", layout="wide")

st.title("AI Hedge Fund — MOEX")
st.caption("AI-анализ акций на Московской бирже")

# --- Sidebar ---
with st.sidebar:
    st.header("Настройки")

    ticker_input = st.text_input(
        "Тикеры (через запятую)",
        value="SBER",
        help="Пример: SBER,GAZP,YDEX,LKOH",
    )

    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("Начальная дата", value=datetime(2026, 3, 1))
    with col2:
        end_date = st.date_input("Конечная дата", value=datetime.now())

    initial_cash = st.number_input("Начальный капитал (руб.)", value=1000000, step=100000)

    show_reasoning = st.checkbox("Показать рассуждения агентов", value=True)

    st.divider()

    analyst_options = [display for display, _ in ANALYST_ORDER]
    selected_analyst_names = st.multiselect(
        "Аналитики",
        options=analyst_options,
        default=analyst_options,
    )

    PROVIDER_KEYS = {
        ModelProvider.GROQ.value: "GROQ_API_KEY",
        ModelProvider.OPENAI.value: "OPENAI_API_KEY",
        ModelProvider.ANTHROPIC.value: "ANTHROPIC_API_KEY",
        ModelProvider.DEEPSEEK.value: "DEEPSEEK_API_KEY",
        ModelProvider.GOOGLE.value: "GOOGLE_API_KEY",
        ModelProvider.OPENROUTER.value: "OPENROUTER_API_KEY",
        ModelProvider.XAI.value: "XAI_API_KEY",
        ModelProvider.GIGACHAT.value: "GIGACHAT_API_KEY",
        ModelProvider.AZURE_OPENAI.value: "AZURE_OPENAI_API_KEY",
        ModelProvider.OLLAMA.value: None,
    }

    available_models = []
    for display, m_name, provider in LLM_ORDER:
        env_key = PROVIDER_KEYS.get(provider)
        if env_key is None or os.getenv(env_key):
            available_models.append((display, m_name, provider))

    if not available_models:
        st.error("API-ключи не найдены. Добавьте ключи в файл .env.")
        st.stop()

    model_options = [f"{display} ({provider})" for display, _, provider in available_models]
    selected_model_idx = st.selectbox(
        "LLM-модель",
        options=range(len(model_options)),
        format_func=lambda i: model_options[i],
        index=0,
    )

    st.divider()
    st.caption("Данные: MOEX ISS API + Smart-Lab (бесплатно)")

# --- Main content ---
tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

selected_analysts = [
    key for display, key in ANALYST_ORDER if display in selected_analyst_names
]

_, model_name, model_provider = available_models[selected_model_idx]

tab_prices, tab_fundamentals, tab_analysis = st.tabs(
    ["Цены", "Фундаментальные", "AI-анализ"]
)

# === Prices tab ===
with tab_prices:
    if st.button("Загрузить цены", key="btn_prices"):
        for ticker in tickers:
            with st.spinner(f"Загрузка цен {ticker}..."):
                prices = get_prices(ticker, str(start_date), str(end_date))
                if not prices:
                    st.warning(f"Нет данных по ценам для {ticker}")
                    continue

                df = pd.DataFrame([p.model_dump() for p in prices])
                df["time"] = pd.to_datetime(df["time"])

                fig = go.Figure(data=[
                    go.Candlestick(
                        x=df["time"], open=df["open"], high=df["high"],
                        low=df["low"], close=df["close"], name=ticker,
                    )
                ])
                fig.update_layout(
                    title=f"{ticker} — {len(prices)} дней",
                    yaxis_title="руб.",
                    xaxis_rangeslider_visible=False,
                    height=400,
                )
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(
                    df[["time", "open", "high", "low", "close", "volume"]]
                    .sort_values("time", ascending=False),
                    hide_index=True, use_container_width=True,
                )

# === Fundamentals tab ===
with tab_fundamentals:
    if st.button("Загрузить фундаментальные данные", key="btn_fund"):
        cols = st.columns(len(tickers))
        for i, ticker in enumerate(tickers):
            with cols[i]:
                st.subheader(ticker)
                with st.spinner(f"Загрузка {ticker}..."):
                    metrics = get_financial_metrics(ticker, str(end_date))
                    if not metrics:
                        st.warning(f"Нет данных для {ticker}")
                        continue

                    m = metrics[0]
                    mc = get_market_cap(ticker, str(end_date))

                    metric_display = {
                        "Капитализация": f"{mc/1e12:.2f} трлн руб." if mc else "Н/Д",
                        "P/E": f"{m.price_to_earnings_ratio:.1f}" if m.price_to_earnings_ratio else "Н/Д",
                        "P/B": f"{m.price_to_book_ratio:.2f}" if m.price_to_book_ratio else "Н/Д",
                        "ROE": f"{m.return_on_equity*100:.1f}%" if m.return_on_equity else "Н/Д",
                        "ROA": f"{m.return_on_assets*100:.1f}%" if m.return_on_assets else "Н/Д",
                        "EPS": f"{m.earnings_per_share:.1f} руб." if m.earnings_per_share else "Н/Д",
                        "EV": f"{m.enterprise_value/1e12:.2f} трлн руб." if m.enterprise_value else "Н/Д",
                        "Валюта": m.currency,
                    }

                    for key, val in metric_display.items():
                        st.metric(key, val)

# === Helpers ===

AGENT_NAMES_RU = {
    "Aswath Damodaran": "Асват Дамодаран",
    "Ben Graham": "Бен Грэм",
    "Bill Ackman": "Билл Акман",
    "Cathie Wood": "Кэти Вуд",
    "Charlie Munger": "Чарли Мангер",
    "Michael Burry": "Майкл Бьюри",
    "Mohnish Pabrai": "Мохниш Пабрай",
    "Nassim Taleb": "Нассим Талеб",
    "Peter Lynch": "Питер Линч",
    "Phil Fisher": "Фил Фишер",
    "Rakesh Jhunjhunwala": "Ракеш Джхунджхунвала",
    "Stanley Druckenmiller": "Стэнли Дракенмиллер",
    "Warren Buffett": "Уоррен Баффет",
    "Technical Analyst": "Технический анализ",
    "Fundamentals Analyst": "Фундаментальный анализ",
    "Growth Analyst": "Анализ роста",
    "News Sentiment": "Сентимент новостей",
    "Sentiment Analyst": "Анализ настроений",
    "Valuation Analyst": "Оценка стоимости",
    "Risk Management": "Управление рисками",
    "Portfolio Manager": "Портфельный менеджер",
}

SIGNAL_LABELS = {
    "BULLISH": ("Покупать", "🟢"),
    "BEARISH": ("Продавать", "🔴"),
    "NEUTRAL": ("Держать", "🟡"),
}

ACTION_LABELS = {
    "BUY": ("Покупка", "🟢"),
    "SELL": ("Продажа", "🔴"),
    "HOLD": ("Держать", "🟡"),
    "COVER": ("Закрыть шорт", "🟢"),
    "SHORT": ("Шорт", "🔴"),
}

KEY_RU = {
    "trend_following": "Тренд", "mean_reversion": "Возврат к среднему",
    "momentum": "Импульс", "volatility": "Волатильность",
    "statistical_arbitrage": "Стат. арбитраж",
    "profitability_signal": "Прибыльность", "growth_signal": "Рост",
    "financial_health_signal": "Фин. здоровье", "price_ratios_signal": "Мультипликаторы",
    "insider_trading": "Инсайдеры", "news_sentiment": "Сентимент новостей",
    "combined_analysis": "Итог", "news_sentiment": "Сентимент новостей",
    "metrics": "метрики", "details": "",
    "adx": "ADX", "trend_strength": "сила тренда",
    "z_score": "Z-score", "rsi_14": "RSI(14)", "rsi_28": "RSI(28)",
    "momentum_1m": "имп. 1м", "momentum_3m": "имп. 3м", "momentum_6m": "имп. 6м",
    "volume_momentum": "объём. имп.", "historical_volatility": "волатильность",
    "price_vs_bb": "цена/BB", "hurst_exponent": "Хёрст",
    "atr_ratio": "ATR%", "skewness": "асимметрия", "kurtosis": "эксцесс",
    "volatility_regime": "режим волат.", "volatility_z_score": "Z волат.",
}


def _is_agent_error(reasoning) -> bool:
    """Detect if an agent returned a real error (not just missing data)."""
    if isinstance(reasoning, str):
        r = reasoning.lower()
        return "error in analysis" in r or "using default" in r or r.startswith("ошибка:")
    return False


def _fmt_val(v):
    """Format a metric value nicely."""
    if isinstance(v, float):
        if abs(v) < 0.01:
            return f"{v:.4f}"
        if abs(v) < 10:
            return f"{v:.2f}"
        return f"{v:.1f}"
    return str(v)


def _format_dict_ru(d, depth=0):
    """Format a structured dict into readable Russian text."""
    if not isinstance(d, dict):
        return str(d)

    parts = []
    for key, val in d.items():
        label = KEY_RU.get(key, key.replace("_", " ").strip())

        if isinstance(val, dict):
            # Signal-with-details/metrics pattern: {"signal": "...", "confidence": N, ...}
            if "signal" in val and "confidence" in val:
                sig = val["signal"]
                conf = val["confidence"]
                line = f"**{label}:** {sig} (уверенность: {conf}%)"
                if "details" in val and val["details"]:
                    line += f"\n{val['details']}"
                if "metrics" in val and isinstance(val["metrics"], dict):
                    m = val["metrics"]
                    metric_str = ", ".join(
                        f"{KEY_RU.get(k, k)}: {_fmt_val(v)}" for k, v in m.items()
                    )
                    line += f"\n{metric_str}"
                parts.append(line)
            elif "signal" in val and "details" in val:
                line = f"**{label}:** {val['signal']}"
                if val.get("details"):
                    line += f". {val['details']}"
                parts.append(line)
            elif depth < 2:
                # Nested dict — recurse
                sub = _format_dict_ru(val, depth + 1)
                if sub:
                    parts.append(f"**{label}:**\n{sub}" if label else sub)
        else:
            if label:
                parts.append(f"{label}: {_fmt_val(val)}")

    indent = "  " * depth
    return ("\n" + indent).join(parts)


def _format_reasoning(reasoning):
    """Format reasoning into readable text — handles dicts, JSON, plain text."""
    if not reasoning:
        return ""

    # Already a dict — format it
    if isinstance(reasoning, dict):
        return _format_dict_ru(reasoning)

    # Try to parse string as JSON
    if isinstance(reasoning, str):
        try:
            parsed = json.loads(reasoning)
            if isinstance(parsed, dict):
                return _format_dict_ru(parsed)
            return str(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    return str(reasoning)


# === AI Analysis tab ===
with tab_analysis:
    st.subheader("Полный AI-анализ")

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.markdown(f"**Модель:** `{model_name}` ({model_provider})")
    with col_info2:
        st.markdown(f"**Аналитиков выбрано:** {len(selected_analysts)}")

    if st.button("Запустить анализ", type="primary", key="btn_full_analysis"):
        if not selected_analysts:
            st.error("Выберите хотя бы одного аналитика в боковой панели.")
        else:
            portfolio = {
                "cash": initial_cash,
                "margin_requirement": 0.0,
                "margin_used": 0.0,
                "positions": {
                    ticker: {
                        "long": 0, "short": 0,
                        "long_cost_basis": 0.0, "short_cost_basis": 0.0,
                        "short_margin_used": 0.0,
                    }
                    for ticker in tickers
                },
                "realized_gains": {
                    ticker: {"long": 0.0, "short": 0.0}
                    for ticker in tickers
                },
            }

            with st.spinner("Выполняется анализ... Это может занять несколько минут."):
                try:
                    result = run_hedge_fund(
                        tickers=tickers,
                        start_date=str(start_date),
                        end_date=str(end_date),
                        portfolio=portfolio,
                        show_reasoning=show_reasoning,
                        selected_analysts=selected_analysts,
                        model_name=model_name,
                        model_provider=model_provider,
                    )
                except Exception as e:
                    st.error(
                        f"**Ошибка при выполнении анализа**\n\n"
                        f"**Тип:** `{type(e).__name__}`\n\n"
                        f"**Сообщение:** `{str(e)}`"
                    )
                    with st.expander("Полный трейс ошибки"):
                        st.code(traceback.format_exc(), language="python")
                    st.stop()

            decisions = result.get("decisions")
            analyst_signals = result.get("analyst_signals", {})

            if not decisions:
                st.warning("Анализ завершён, но торговые решения не были получены.")
            else:
                # --- Agent Signals ---
                st.subheader("Сигналы агентов")

                for ticker in tickers:
                    st.markdown(f"#### {ticker}")

                    signal_rows = []
                    for agent, signals in analyst_signals.items():
                        if agent == "risk_management_agent" or ticker not in signals:
                            continue

                        sig = signals[ticker]
                        signal_type = sig.get("signal", "").upper()
                        confidence = sig.get("confidence", 0)
                        reasoning = sig.get("reasoning", "")
                        agent_display = agent.replace("_agent", "").replace("_", " ").title()
                        is_error = _is_agent_error(reasoning)

                        signal_rows.append({
                            "Agent": agent_display,
                            "Signal": signal_type,
                            "Confidence": confidence,
                            "Reasoning": reasoning,
                            "IsError": is_error,
                        })

                    if signal_rows:
                        order_map = {display: idx for idx, (display, _) in enumerate(ANALYST_ORDER)}
                        signal_rows.sort(key=lambda r: order_map.get(r["Agent"], 999))

                        for row in signal_rows:
                            agent_ru = AGENT_NAMES_RU.get(row["Agent"], row["Agent"])

                            if row["IsError"]:
                                label = f"❌ **{agent_ru}** — Ошибка"
                                with st.expander(label):
                                    error_text = str(row["Reasoning"])
                                    st.error(error_text)
                            else:
                                sig_ru, emoji = SIGNAL_LABELS.get(row["Signal"], (row["Signal"], "⚪"))
                                conf = row["Confidence"]
                                label = f"{emoji} **{agent_ru}** — {sig_ru} ({conf}%)"

                                if show_reasoning:
                                    with st.expander(label):
                                        st.markdown(_format_reasoning(row["Reasoning"]))
                                else:
                                    st.markdown(label)

                # --- Trading Decisions ---
                st.subheader("Торговые решения")

                for ticker, decision in decisions.items():
                    action = decision.get("action", "").upper()
                    confidence = decision.get("confidence", 0)
                    quantity = decision.get("quantity", 0)
                    reasoning = decision.get("reasoning", "")

                    action_ru, action_emoji = ACTION_LABELS.get(action, (action, "⚪"))

                    col1, col2, col3 = st.columns(3)
                    col1.metric(f"{ticker} — Действие", f"{action_emoji} {action_ru}")
                    col2.metric("Количество", f"{quantity:,}")
                    col3.metric("Уверенность", f"{confidence:.1f}%")

                    if show_reasoning and reasoning:
                        st.markdown(_format_reasoning(reasoning))

                    st.divider()

                # --- Portfolio Summary ---
                st.subheader("Сводка по портфелю")

                summary_rows = []
                for ticker, decision in decisions.items():
                    action = decision.get("action", "").upper()
                    action_ru, _ = ACTION_LABELS.get(action, (action, ""))

                    bullish = bearish = neutral = errors = 0
                    for agent, signals in analyst_signals.items():
                        if agent == "risk_management_agent" or ticker not in signals:
                            continue
                        sig = signals[ticker]
                        s = sig.get("signal", "").upper()
                        reas = sig.get("reasoning", "")

                        if _is_agent_error(reas):
                            errors += 1
                        elif s == "BULLISH":
                            bullish += 1
                        elif s == "BEARISH":
                            bearish += 1
                        elif s == "NEUTRAL":
                            neutral += 1

                    summary_rows.append({
                        "Тикер": ticker,
                        "Действие": action_ru,
                        "Количество": decision.get("quantity", 0),
                        "Уверенность": f"{decision.get('confidence', 0):.1f}%",
                        "Покупать": bullish,
                        "Продавать": bearish,
                        "Держать": neutral,
                        "Ошибки": errors,
                    })

                st.dataframe(summary_rows, hide_index=True, use_container_width=True)

st.divider()
st.caption("AI Hedge Fund MOEX — Только для образовательных целей. Не является инвестиционной рекомендацией.")
