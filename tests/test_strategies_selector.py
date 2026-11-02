import pandas as pd
import pytest

from claudeupbot.regime import Regime
from claudeupbot.selector import StrategySelector, entries_allowed
from claudeupbot.strategies import ALL_STRATEGIES


@pytest.mark.parametrize("name", list(ALL_STRATEGIES))
def test_signals_shape_and_range(name, candles):
    sig = ALL_STRATEGIES[name]().generate(candles)
    assert sig.index.equals(candles.index)
    assert sig.between(0, 1).all()


@pytest.mark.parametrize("name", list(ALL_STRATEGIES))
def test_signals_have_no_lookahead(name, candles):
    strat = ALL_STRATEGIES[name]()
    full = strat.generate(candles)
    for cut in (200, 350):
        assert strat.generate(candles.iloc[:cut]).equals(full.iloc[:cut])


def test_selector_maps_regimes():
    sel = StrategySelector()
    assert sel.select(Regime.BULLISH).name == "trend_following"
    assert sel.select(Regime.SIDEWAYS).name == "mean_reversion"
    assert sel.select(Regime.VOLATILE).name == "volatility_breakout"
    assert sel.select(Regime.BEARISH).name == "defensive_cash"


def test_selector_uses_breakout_at_open_in_sideways():
    assert StrategySelector().select(Regime.SIDEWAYS, pd.Timestamp("2024-05-02 09:15")).name == "volatility_breakout"


def test_entry_window():
    assert not entries_allowed(pd.Timestamp("2024-05-02 09:15"))
    assert entries_allowed(pd.Timestamp("2024-05-02 11:00"))
    assert not entries_allowed(pd.Timestamp("2024-05-02 15:15"))
    assert entries_allowed(pd.Timestamp("2024-05-02"))  # daily bar
