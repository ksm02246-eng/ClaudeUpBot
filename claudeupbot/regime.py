"""Market regime detection: bullish, bearish, sideways or volatile."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from . import indicators as ind


class Regime(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"  # not enough history yet


@dataclass(frozen=True)
class RegimeParams:
    fast: int = 20
    slow: int = 50
    adx_period: int = 14
    adx_trend: float = 22.0
    atr_period: int = 14
    vol_lookback: int = 100
    vol_percentile: float = 0.85


def classify_series(df: pd.DataFrame, params: RegimeParams = RegimeParams()) -> pd.Series:
    """Label every bar with a regime using only data available up to that bar.

    Rules, checked in order:
      1. VOLATILE  - ATR as % of price is in the top (1 - vol_percentile) of its recent history.
      2. BULLISH   - ADX shows a trend, fast EMA above slow EMA, and price above slow EMA.
      3. BEARISH   - ADX shows a trend, fast EMA below slow EMA, and price below slow EMA.
      4. SIDEWAYS  - everything else.
    """
    close = df["close"]
    fast = ind.ema(close, params.fast)
    slow = ind.ema(close, params.slow)
    adx = ind.adx(df, params.adx_period)
    atr_pct = ind.atr(df, params.atr_period) / close
    # Percentile rank of the current ATR% inside its trailing window (causal).
    vol_rank = atr_pct.rolling(params.vol_lookback, min_periods=params.vol_lookback // 2).rank(pct=True)

    labels = pd.Series(Regime.SIDEWAYS.value, index=df.index, dtype=object)
    trending = adx > params.adx_trend
    labels[trending & (fast > slow) & (close > slow)] = Regime.BULLISH.value
    labels[trending & (fast < slow) & (close < slow)] = Regime.BEARISH.value
    labels[vol_rank > params.vol_percentile] = Regime.VOLATILE.value

    warm = slow.notna() & adx.notna() & vol_rank.notna()
    labels[~warm] = Regime.UNKNOWN.value
    return labels


def current_regime(df: pd.DataFrame, params: RegimeParams = RegimeParams()) -> Regime:
    if df.empty:
        return Regime.UNKNOWN
    return Regime(classify_series(df, params).iloc[-1])
