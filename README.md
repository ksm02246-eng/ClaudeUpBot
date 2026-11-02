# ClaudeUpBot

A regime-aware trading bot for [Upstox](https://upstox.com/developer/api-documentation) that
detects whether the market is **bullish, bearish, sideways or volatile**, switches strategy to
match (and by time of day), and trades **only with cash already in the wallet**.

> Paper trading is the default. Real orders are sent only when `LIVE_TRADING=true`.

## What's inside

| Part | File | What it does |
|---|---|---|
| Regime detection | `claudeupbot/regime.py` | EMA 20/50 + ADX for trend, ATR% percentile for volatility |
| Strategies | `claudeupbot/strategies/` | One per regime (table below) |
| Selector | `claudeupbot/selector.py` | Regime → strategy, plus time-of-day rules |
| Wallet guard | `claudeupbot/risk.py` | Delivery-only, no margin/MTF/shorting, capital and daily-loss caps |
| Backtester | `claudeupbot/backtest.py` | Cash-only, next-bar-open fills, costs, metrics vs buy & hold |
| Brokers | `claudeupbot/brokers/` | `PaperBroker` (JSON state) and `UpstoxBroker` (REST v2) |
| Engine | `claudeupbot/engine.py` | One cycle: data → regime → strategy → guard → order → journal |
| Scheduler | `claudeupbot/scheduler.py`, `deploy/` | Runs every N minutes in NSE hours; systemd and cron examples |
| UI | `ui/app.py` | Streamlit: backtests, trade journal, settings |

### Strategy per market regime

| Regime | Strategy | Idea |
|---|---|---|
| Bullish | `trend_following` | EMA crossover entry, 3×ATR trailing stop |
| Sideways | `mean_reversion` | Buy lower Bollinger band with RSI ≤ 35, sell at the mean |
| Volatile | `volatility_breakout` | 20-bar Donchian breakout at half size, exit on 10-bar low |
| Bearish | `defensive_cash` | Exit to cash (shorting needs margin, which is not allowed) |

**Timing rules (IST):** no new buys before 09:30 or after 15:00; in the first 15 minutes a
sideways reading uses breakout logic because opening gaps run over mean-reversion trades.
Exits are always allowed.

### Wallet-only rules (enforced in `risk.py` and again in `UpstoxBroker`)

- Product is always `D` (delivery, fully paid). `I` (intraday) and `MTF` are rejected.
- Buys never exceed available cash minus `CASH_BUFFER_PCT`, and never push total deployed
  capital above `MAX_CAPITAL`.
- No selling more than you hold, so no short selling.
- Each instrument is capped at `MAX_POSITION_PCT` of `MAX_CAPITAL`.
- New buys stop for the day once the loss passes `MAX_DAILY_LOSS_PCT`.

Upstox's `available_margin` can include collateral from pledged shares, so set `MAX_CAPITAL`
to the cash you actually want the bot to use.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[ui,dev]"
pytest -q                                   # run the tests
python -m claudeupbot backtest              # backtest on synthetic data
python -m claudeupbot backtest --csv my.csv --strategy auto --trades
streamlit run ui/app.py                     # dashboard
```

CSV format: `timestamp,open,high,low,close,volume`.

## Connecting Upstox

1. Create an app at <https://account.upstox.com/developer/apps> and note the API key, secret
   and redirect URL.
2. `cp .env.example .env` and fill `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_REDIRECT_URI`.
3. Each trading day: `python -m claudeupbot login-url`, open it, log in, copy the `code` from the
   redirect URL, then `python -m claudeupbot exchange-code <code>` and put the token in
   `UPSTOX_ACCESS_TOKEN` (tokens expire around 03:30 IST).
4. `python -m claudeupbot check` confirms the connection and shows wallet cash.
5. `python -m claudeupbot run` trades on paper every `RUN_EVERY_MINUTES` during market hours.
   Watch the journal in the UI for a while before even considering `LIVE_TRADING=true`.

## Running on its own

Use `deploy/claudeupbot.service` (systemd, long-running) or `deploy/crontab.example` (one
cycle per cron tick). Exchange holidays aren't modelled; the broker rejects orders on those days.

## Not done yet

- Put-option buying for bearish markets (wallet-paid, but needs option-chain handling).
- Exchange holiday calendar and automated daily token refresh.
- Parameter tuning on real NSE data; the defaults are untested starting points, not advice.
