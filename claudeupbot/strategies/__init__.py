from .base import Strategy
from .breakout import VolatilityBreakout
from .defensive import Defensive
from .mean_reversion import MeanReversion
from .trend import TrendFollowing

ALL_STRATEGIES: dict[str, type[Strategy]] = {
    cls.name: cls for cls in (TrendFollowing, MeanReversion, VolatilityBreakout, Defensive)
}

__all__ = ["Strategy", "TrendFollowing", "MeanReversion", "VolatilityBreakout", "Defensive", "ALL_STRATEGIES"]
