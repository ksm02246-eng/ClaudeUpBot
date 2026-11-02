from __future__ import annotations

import pandas as pd

from .. import indicators as ind
from .base import Strategy


class VolatilityBreakout(Strategy):
    """Volatile markets: only buy confirmed upside breakouts, with a tight channel exit
    and half-size exposure to respect the larger swings."""

    name = "volatility_breakout"
    description = "Donchian channel breakout, half size, exit on short channel low"

    def __init__(self, entry_window: int = 20, exit_window: int = 10, size: float = 0.5):
        self.entry_window, self.exit_window, self.size = entry_window, exit_window, size

    def generate(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        upper = df["high"].rolling(self.entry_window).max().shift(1)
        lower = df["low"].rolling(self.exit_window).min().shift(1)
        out = []
        pos = 0.0
        for c, up, lo in zip(close, upper, lower):
            if pd.isna(up) or pd.isna(lo):
                out.append(0.0)
                continue
            if pos == 0.0 and c > up:
                pos = self.size
            elif pos > 0.0 and c < lo:
                pos = 0.0
            out.append(pos)
        return pd.Series(out, index=df.index)
