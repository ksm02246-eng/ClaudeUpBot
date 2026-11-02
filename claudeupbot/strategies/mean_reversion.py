from __future__ import annotations

import pandas as pd

from .. import indicators as ind
from .base import Strategy


class MeanReversion(Strategy):
    """Sideways markets: buy oversold dips at the lower Bollinger band, sell back at the mean."""

    name = "mean_reversion"
    description = "Bollinger band + RSI dip buying, exit at middle band"

    def __init__(self, window: int = 20, num_std: float = 2.0, rsi_entry: float = 35, rsi_exit: float = 55,
                 stop_pct: float = 0.05):
        self.window, self.num_std = window, num_std
        self.rsi_entry, self.rsi_exit, self.stop_pct = rsi_entry, rsi_exit, stop_pct

    def generate(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        lower, mid, _ = ind.bollinger(close, self.window, self.num_std)
        r = ind.rsi(close)
        out = []
        pos, entry = 0.0, 0.0
        for c, lo, m, rv in zip(close, lower, mid, r):
            if pd.isna(lo) or pd.isna(rv):
                out.append(0.0)
                continue
            if pos == 0.0 and c <= lo and rv <= self.rsi_entry:
                pos, entry = 1.0, c
            elif pos == 1.0 and (c >= m or rv >= self.rsi_exit or c <= entry * (1 - self.stop_pct)):
                pos = 0.0
            out.append(pos)
        return pd.Series(out, index=df.index)
