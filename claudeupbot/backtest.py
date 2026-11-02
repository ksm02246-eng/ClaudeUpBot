"""Cash-only backtester: signals at bar t are filled at bar t+1's open."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .regime import Regime, RegimeParams, classify_series
from .selector import StrategySelector, entries_allowed
from .strategies import Strategy


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    regimes: pd.Series
    strategy_used: pd.Series
    metrics: dict = field(default_factory=dict)


def _periods_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return 252.0
    step = pd.Series(index).diff().median()
    if step >= pd.Timedelta(hours=20):
        return 252.0
    bars_per_day = max(int(pd.Timedelta(hours=6, minutes=15) / step), 1)
    return 252.0 * bars_per_day


def run_backtest(
    df: pd.DataFrame,
    initial_cash: float = 100_000.0,
    selector: StrategySelector | None = None,
    fixed_strategy: Strategy | None = None,
    cost_pct: float = 0.0012,
    allocation: float = 1.0,
    regime_params: RegimeParams = RegimeParams(),
) -> BacktestResult:
    """Simulate trading one instrument with cash only.

    If ``fixed_strategy`` is given it is used for every bar; otherwise the
    selector switches strategy according to the detected regime and time.
    ``cost_pct`` approximates brokerage + STT + exchange charges per side.
    """
    if len(df) < 2:
        raise ValueError("need at least 2 candles")
    selector = selector or StrategySelector()
    regimes = classify_series(df, regime_params)

    if fixed_strategy is not None:
        signals = {fixed_strategy.name: fixed_strategy.generate(df)}
        chosen = pd.Series(fixed_strategy.name, index=df.index)
    else:
        signals = {s.name: s.generate(df) for s in set(selector.mapping.values())}
        chosen = pd.Series(
            [selector.select(Regime(r), ts).name for r, ts in zip(regimes, df.index)], index=df.index
        )

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    cash, qty = float(initial_cash), 0
    entry_price = 0.0
    equity, trades = [], []
    exposure = 0.0  # target exposure carried from the previous bar

    for i, ts in enumerate(df.index):
        # 1) fill yesterday's decision at today's open
        if i > 0:
            price = opens[i]
            equity_now = cash + qty * price
            target_value = exposure * allocation * equity_now
            target_qty = int(math.floor(target_value / (price * (1 + cost_pct)))) if exposure > 0 else 0
            if target_qty > qty:
                buy = min(target_qty - qty, int(cash // (price * (1 + cost_pct))))
                if buy > 0:
                    cost = buy * price * (1 + cost_pct)
                    cash -= cost
                    entry_price = (entry_price * qty + buy * price) / (qty + buy)
                    qty += buy
                    trades.append({"time": ts, "side": "BUY", "qty": buy, "price": price,
                                   "strategy": chosen.iloc[i - 1], "regime": regimes.iloc[i - 1], "pnl": 0.0})
            elif target_qty < qty:
                sell = qty - target_qty
                proceeds = sell * price * (1 - cost_pct)
                pnl = proceeds - sell * entry_price * (1 + cost_pct)
                cash += proceeds
                qty -= sell
                trades.append({"time": ts, "side": "SELL", "qty": sell, "price": price,
                               "strategy": chosen.iloc[i - 1], "regime": regimes.iloc[i - 1], "pnl": pnl})
                if qty == 0:
                    entry_price = 0.0
        assert cash >= -1e-6, "backtester must never go below zero cash"

        # 2) decide tomorrow's exposure from data up to today's close
        wanted = float(signals[chosen.iloc[i]].iloc[i])
        current = (qty * closes[i]) / max(cash + qty * closes[i], 1e-9)
        if wanted > current + 1e-9 and not entries_allowed(ts):
            wanted = exposure  # no new buying outside the entry window
        exposure = wanted
        equity.append(cash + qty * closes[i])

    equity_s = pd.Series(equity, index=df.index, name="equity")
    trades_df = pd.DataFrame(trades, columns=["time", "side", "qty", "price", "strategy", "regime", "pnl"])
    metrics = compute_metrics(equity_s, trades_df, df, initial_cash)
    return BacktestResult(equity_s, trades_df, regimes, chosen, metrics)


def compute_metrics(equity: pd.Series, trades: pd.DataFrame, df: pd.DataFrame, initial_cash: float) -> dict:
    rets = equity.pct_change().dropna()
    ppy = _periods_per_year(equity.index)
    years = max(len(equity) / ppy, 1e-9)
    total = equity.iloc[-1] / initial_cash - 1
    dd = equity / equity.cummax() - 1
    sells = trades[trades["side"] == "SELL"] if not trades.empty else trades
    sharpe = float(rets.mean() / rets.std() * np.sqrt(ppy)) if len(rets) > 1 and rets.std() > 0 else 0.0
    return {
        "final_equity": round(float(equity.iloc[-1]), 2),
        "total_return_pct": round(100 * total, 2),
        "cagr_pct": round(100 * ((1 + total) ** (1 / years) - 1), 2) if total > -1 else -100.0,
        "max_drawdown_pct": round(100 * float(dd.min()), 2),
        "sharpe": round(sharpe, 2),
        "trades": int(len(trades)),
        "win_rate_pct": round(100 * float((sells["pnl"] > 0).mean()), 1) if len(sells) else 0.0,
        "buy_and_hold_return_pct": round(100 * (df["close"].iloc[-1] / df["open"].iloc[0] - 1), 2),
    }
