from __future__ import annotations

import pandas as pd

from .. import indicators as ind
from .base import Strategy


class TrendFollowing(Strategy):
    """Bullish markets: ride the trend with an EMA crossover, exit on a trailing ATR stop."""

    name = "trend_following"
    description = "EMA fast/slow crossover with ATR trailing stop"

    def __init__(self, fast: int = 20, slow: int = 50, atr_mult: float = 3.0):
        self.fast, self.slow, self.atr_mult = fast, slow, atr_mult

    def generate(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        fast = ind.ema(close, self.fast)
        slow = ind.ema(close, self.slow)
        atr = ind.atr(df)
        out = []
        pos, peak = 0.0, 0.0
        for c, f, s, a in zip(close, fast, slow, atr):
            if pd.isna(f) or pd.isna(s) or pd.isna(a):
                out.append(0.0)
                continue
            if pos == 0.0 and f > s and c > f:
                pos, peak = 1.0, c
            elif pos == 1.0:
                peak = max(peak, c)
                if f < s or c < peak - self.atr_mult * a:
                    pos = 0.0
            out.append(pos)
        return pd.Series(out, index=df.index)
