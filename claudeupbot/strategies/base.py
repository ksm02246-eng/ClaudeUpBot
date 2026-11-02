"""Strategy interface.

Every strategy returns a *target exposure* per bar: 1.0 = fully invested in the
instrument (up to the risk limits), 0.0 = flat. Strategies are long-only because
the bot only trades with cash in the wallet (no short selling, no margin).
Signals at bar t only use data up to and including bar t; the backtester fills
them at the next bar's open.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of target exposure (0.0..1.0) aligned to df.index."""

    def latest(self, df: pd.DataFrame) -> float:
        sig = self.generate(df)
        return float(sig.iloc[-1]) if len(sig) else 0.0
