"""Streamlit GUI for AI Hedge Fund (MOEX)."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from src.tools.api import get_prices, get_financial_metrics, get_market_cap
from src.utils.analysts import ANALYST_ORDER

st.set_page_config(page_title="AI Hedge Fund — MOEX", page_icon="📈", layout="wide")

st.title("AI Hedge Fund — MOEX")
st.caption("AI-powered analysis of Russian stocks (Moscow Exchange)")

# --- Sidebar ---
with st.sidebar:
    st.header("Settings")

    ticker_input = st.text_input(
        "Tickers (comma-separated)",
        value="SBER",
        help="Example: SBER,GAZP,YDEX,LKOH",
    )

    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("Start date", value=datetime(2026, 3, 1))
    with col2:
        end_date = st.date_input("End date", value=datetime.now())

    initial_cash = st.number_input("Initial cash (RUB)", value=1000000, step=100000)

    show_reasoning = st.checkbox("Show agent reasoning", value=True)

    st.divider()
    st.caption("Data: MOEX ISS API + Smart-Lab (free)")

# --- Main content ---
tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

tab_prices, tab_fundamentals, tab_analysis = st.tabs(
    ["Prices", "Fundamentals", "AI Analysis"]
)

# === Prices tab ===
with tab_prices:
    if st.button("Load prices", key="btn_prices"):
        for ticker in tickers:
            with st.spinner(f"Loading {ticker} prices..."):
                prices = get_prices(ticker, str(start_date), str(end_date))
                if not prices:
                    st.warning(f"No price data for {ticker}")
                    continue

                df = pd.DataFrame([p.model_dump() for p in prices])
                df["time"] = pd.to_datetime(df["time"])

                # Candlestick chart
                fig = go.Figure(data=[
                    go.Candlestick(
                        x=df["time"],
                        open=df["open"],
                        high=df["high"],
                        low=df["low"],
                        close=df["close"],
                        name=ticker,
                    )
                ])
                fig.update_layout(
                    title=f"{ticker} — {len(prices)} days",
                    yaxis_title="RUB",
                    xaxis_rangeslider_visible=False,
                    height=400,
                )
                st.plotly_chart(fig, use_container_width=True)

                # Price table
                st.dataframe(
                    df[["time", "open", "high", "low", "close", "volume"]].sort_values("time", ascending=False),
                    hide_index=True,
                    use_container_width=True,
                )

# === Fundamentals tab ===
with tab_fundamentals:
    if st.button("Load fundamentals", key="btn_fund"):
        cols = st.columns(len(tickers))
        for i, ticker in enumerate(tickers):
            with cols[i]:
                st.subheader(ticker)
                with st.spinner(f"Loading {ticker}..."):
                    metrics = get_financial_metrics(ticker, str(end_date))
                    if not metrics:
                        st.warning(f"No data for {ticker}")
                        continue

                    m = metrics[0]
                    mc = get_market_cap(ticker, str(end_date))

                    metric_display = {
                        "Market Cap": f"{mc/1e12:.2f}T RUB" if mc else "N/A",
                        "P/E": f"{m.price_to_earnings_ratio:.1f}" if m.price_to_earnings_ratio else "N/A",
                        "P/B": f"{m.price_to_book_ratio:.2f}" if m.price_to_book_ratio else "N/A",
                        "ROE": f"{m.return_on_equity*100:.1f}%" if m.return_on_equity else "N/A",
                        "ROA": f"{m.return_on_assets*100:.1f}%" if m.return_on_assets else "N/A",
                        "EPS": f"{m.earnings_per_share:.1f} RUB" if m.earnings_per_share else "N/A",
                        "EV": f"{m.enterprise_value/1e12:.2f}T RUB" if m.enterprise_value else "N/A",
                        "Currency": m.currency,
                    }

                    for key, val in metric_display.items():
                        st.metric(key, val)

# === AI Analysis tab ===
with tab_analysis:
    st.info("Run the full analysis from CLI: `python -m src.main --tickers {} --analysts-all --show-reasoning`".format(
        ",".join(tickers)
    ))

    st.markdown("### Available Analysts")
    analyst_data = []
    for display_name, agent_name in ANALYST_ORDER:
        analyst_data.append({"Analyst": display_name, "Agent": agent_name})
    st.dataframe(analyst_data, hide_index=True, use_container_width=True)

    st.markdown("### Quick analysis (prices + fundamentals only)")
    if st.button("Run quick analysis", key="btn_analysis"):
        results = []
        for ticker in tickers:
            with st.spinner(f"Analyzing {ticker}..."):
                prices = get_prices(ticker, str(start_date), str(end_date))
                metrics = get_financial_metrics(ticker, str(end_date))
                mc = get_market_cap(ticker, str(end_date))

                if prices:
                    latest = prices[-1]
                    change = ((latest.close - prices[0].open) / prices[0].open) * 100
                    results.append({
                        "Ticker": ticker,
                        "Price": f"{latest.close:.2f}",
                        "Change": f"{change:+.1f}%",
                        "Volume": f"{latest.volume:,}",
                        "Market Cap": f"{mc/1e12:.2f}T" if mc else "N/A",
                        "P/E": f"{metrics[0].price_to_earnings_ratio:.1f}" if metrics and metrics[0].price_to_earnings_ratio else "N/A",
                        "ROE": f"{metrics[0].return_on_equity*100:.1f}%" if metrics and metrics[0].return_on_equity else "N/A",
                        "Signal": "—",
                    })

        if results:
            st.dataframe(results, hide_index=True, use_container_width=True)

st.divider()
st.caption("AI Hedge Fund MOEX — Educational purposes only. Not investment advice.")
