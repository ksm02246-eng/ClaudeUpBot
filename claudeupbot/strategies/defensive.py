from __future__ import annotations

import pandas as pd

from .base import Strategy


class Defensive(Strategy):
    """Bearish markets: stay in cash.

    Without margin the bot cannot short stocks, so the safest wallet-only response
    to a downtrend is to exit longs and preserve capital. (Buying put options is
    also fully paid from the wallet and could be added later as an opt-in.)
    """

    name = "defensive_cash"
    description = "Exit to cash; no new longs in a downtrend"

    def generate(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(0.0, index=df.index)
