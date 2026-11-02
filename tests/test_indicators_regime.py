import numpy as np
import pandas as pd

from claudeupbot import indicators as ind
from claudeupbot.regime import Regime, classify_series


def _trend(n=300, drift=0.004, vol=0.004, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({"open": close, "high": close * 1.003, "low": close * 0.997, "close": close,
                         "volume": 1.0}, index=idx)


def test_rsi_bounds(candles):
    r = ind.rsi(candles["close"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_indicators_are_causal(candles):
    full = ind.adx(candles)
    part = ind.adx(candles.iloc[:300])
    pd.testing.assert_series_equal(full.iloc[:300], part)


def test_uptrend_is_bullish():
    labels = classify_series(_trend(drift=0.004))
    assert (labels.iloc[-50:] == Regime.BULLISH.value).mean() > 0.6


def test_downtrend_is_bearish():
    labels = classify_series(_trend(drift=-0.004))
    assert (labels.iloc[-50:] == Regime.BEARISH.value).mean() > 0.6


def test_vol_spike_is_volatile():
    df = _trend(drift=0.0, vol=0.003)
    rng = np.random.default_rng(1)
    shock = df.iloc[-20:].copy()
    noise = np.exp(np.cumsum(rng.normal(0, 0.05, 20)))
    for c in ("open", "close"):
        shock[c] = shock[c] * noise
    shock["high"] = shock[["open", "close"]].max(axis=1) * 1.04
    shock["low"] = shock[["open", "close"]].min(axis=1) * 0.96
    df.iloc[-20:] = shock
    assert classify_series(df).iloc[-1] == Regime.VOLATILE.value


def test_warmup_is_unknown(candles):
    assert classify_series(candles).iloc[0] == Regime.UNKNOWN.value
