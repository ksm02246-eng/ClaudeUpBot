"""ClaudeUpBot dashboard. Run with: streamlit run ui/app.py"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claudeupbot.backtest import run_backtest  # noqa: E402
from claudeupbot.config import Settings  # noqa: E402
from claudeupbot.data import load_csv, synthetic_candles  # noqa: E402
from claudeupbot.strategies import ALL_STRATEGIES  # noqa: E402

st.set_page_config(page_title="ClaudeUpBot", layout="wide")
st.title("ClaudeUpBot")
settings = Settings.from_env()
st.caption(f"Mode: **{'LIVE' if settings.live_trading else 'PAPER'}** · wallet-only (delivery, no margin, no shorting)"
           f" · capital cap ₹{settings.max_capital:,.0f}")

tab_bt, tab_journal, tab_cfg = st.tabs(["Backtest", "Trade journal", "Settings"])

with tab_bt:
    with st.sidebar:
        st.header("Backtest")
        source = st.radio("Data", ["Synthetic sample", "Upload CSV"])
        upload = st.file_uploader("CSV: timestamp,open,high,low,close,volume", type="csv") \
            if source == "Upload CSV" else None
        strategy = st.selectbox("Strategy", ["auto (switch by regime)", *ALL_STRATEGIES])
        cash = st.number_input("Starting cash (₹)", 1_000.0, 10_000_000.0, 100_000.0, step=10_000.0)
        cost = st.number_input("Cost per side (%)", 0.0, 1.0, 0.12, step=0.01) / 100
        seed = st.number_input("Synthetic seed", 0, 10_000, 7) if source == "Synthetic sample" else 7
        go = st.button("Run backtest", type="primary")

    if go:
        if source == "Upload CSV" and upload is None:
            st.warning("Upload a CSV first.")
            st.stop()
        df = load_csv(upload) if upload is not None else synthetic_candles(seed=int(seed))
        fixed = None if strategy.startswith("auto") else ALL_STRATEGIES[strategy]()
        res = run_backtest(df, initial_cash=cash, fixed_strategy=fixed, cost_pct=cost)

        m = res.metrics
        cols = st.columns(5)
        cols[0].metric("Return", f"{m['total_return_pct']}%", f"B&H {m['buy_and_hold_return_pct']}%")
        cols[1].metric("Max drawdown", f"{m['max_drawdown_pct']}%")
        cols[2].metric("Sharpe", m["sharpe"])
        cols[3].metric("Trades", m["trades"])
        cols[4].metric("Win rate", f"{m['win_rate_pct']}%")

        bh = df["close"] / df["open"].iloc[0] * cash
        st.subheader("Equity vs buy & hold")
        st.line_chart(pd.DataFrame({"strategy": res.equity, "buy & hold": bh}))

        st.subheader("Price and detected regime")
        st.line_chart(df["close"])
        mix = (res.regimes.value_counts(normalize=True) * 100).round(1).rename("% of bars")
        c1, c2 = st.columns(2)
        c1.dataframe(mix)
        c2.dataframe(res.strategy_used.value_counts().rename("bars"))

        st.subheader("Trades")
        st.dataframe(res.trades, width="stretch")
    else:
        st.info("Pick data and a strategy in the sidebar, then run a backtest.")

with tab_journal:
    path = settings.journal_path
    if os.path.exists(path):
        with open(path) as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        st.dataframe(pd.DataFrame(rows).iloc[::-1], width="stretch")
    else:
        st.info(f"No journal yet at {path}. Start the bot with `python -m claudeupbot run`.")

with tab_cfg:
    missing = settings.missing_live_credentials()
    if missing:
        st.warning("Missing for Upstox: " + ", ".join(missing) + ". Add them to `.env` (see `.env.example`).")
    st.json({k: v for k, v in settings.__dict__.items() if "token" not in k and "secret" not in k})
