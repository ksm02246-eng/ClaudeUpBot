import pytest

from claudeupbot.data import synthetic_candles


@pytest.fixture(scope="session")
def candles():
    return synthetic_candles(n_days=500, seed=3)
