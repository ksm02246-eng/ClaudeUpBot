"""Pick a strategy from the market regime and the time of day (IST)."""

from __future__ import annotations

from datetime import time

import pandas as pd

from .regime import Regime
from .strategies import Defensive, MeanReversion, Strategy, TrendFollowing, VolatilityBreakout

# NSE cash session (IST)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
# Skip the noisy opening auction spillover and the closing rush for *new* entries.
ENTRY_START = time(9, 30)
ENTRY_END = time(15, 0)


class StrategySelector:
    def __init__(self, mapping: dict[Regime, Strategy] | None = None):
        self.mapping = mapping or {
            Regime.BULLISH: TrendFollowing(),
            Regime.SIDEWAYS: MeanReversion(),
            Regime.VOLATILE: VolatilityBreakout(),
            Regime.BEARISH: Defensive(),
            Regime.UNKNOWN: Defensive(),
        }

    def select(self, regime: Regime, ts: pd.Timestamp | None = None) -> Strategy:
        strategy = self.mapping.get(regime, self.mapping[Regime.UNKNOWN])
        # Around the open, sideways reversion trades get run over by gap moves;
        # prefer breakout logic until the market settles.
        if ts is not None and _has_clock(ts) and ts.time() < ENTRY_START and regime == Regime.SIDEWAYS:
            return self.mapping[Regime.VOLATILE]
        return strategy


def _has_clock(ts: pd.Timestamp) -> bool:
    return ts.time() != time(0, 0)


def entries_allowed(ts: pd.Timestamp) -> bool:
    """New buys only inside the entry window. Daily bars (00:00) are always allowed."""
    if not _has_clock(ts):
        return True
    return ENTRY_START <= ts.time() <= ENTRY_END
