"""Candle data helpers: CSV loading and a synthetic regime-switching generator for offline tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED = ["open", "high", "low", "close", "volume"]


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    for alias in ("timestamp", "date", "datetime", "time"):
        if alias in df.columns:
            df[alias] = pd.to_datetime(df[alias])
            df = df.set_index(alias)
            break
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    df.index = pd.DatetimeIndex(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
    df.index.name = "timestamp"
    return df[REQUIRED].astype(float).sort_index()


def load_csv(path_or_buffer) -> pd.DataFrame:
    return normalise(pd.read_csv(path_or_buffer))


def synthetic_candles(n_days: int = 750, seed: int = 7, start_price: float = 1000.0) -> pd.DataFrame:
    """Daily candles that cycle through bull, sideways, volatile and bear phases."""
    rng = np.random.default_rng(seed)
    phases = [  # (drift per day, daily vol)
        (0.0015, 0.010),   # bullish
        (0.0000, 0.008),   # sideways
        (0.0003, 0.030),   # volatile
        (-0.0015, 0.012),  # bearish
    ]
    rets = []
    while len(rets) < n_days:
        drift, vol = phases[len(rets) // 90 % len(phases)]
        rets.extend(rng.normal(drift, vol, size=90))
    rets = np.array(rets[:n_days])
    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]]) * (1 + rng.normal(0, 0.002, n_days))
    spread = np.abs(rng.normal(0, 0.008, n_days)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(100_000, 1_000_000, n_days).astype(float)
    idx = pd.bdate_range("2022-01-03", periods=n_days, name="timestamp")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)
