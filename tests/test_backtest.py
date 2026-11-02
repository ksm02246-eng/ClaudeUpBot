import pytest

from claudeupbot.backtest import run_backtest
from claudeupbot.data import synthetic_candles
from claudeupbot.strategies import Defensive, TrendFollowing


def test_backtest_runs_and_never_borrows(candles):
    res = run_backtest(candles, initial_cash=50_000)
    assert len(res.equity) == len(candles)
    assert (res.equity > 0).all()
    assert set(res.trades["side"]) <= {"BUY", "SELL"}
    # holdings never go negative => no short selling
    pos = 0
    for _, t in res.trades.iterrows():
        pos += t.qty if t.side == "BUY" else -t.qty
        assert pos >= 0


def test_defensive_never_trades(candles):
    res = run_backtest(candles, fixed_strategy=Defensive())
    assert res.trades.empty
    assert res.metrics["total_return_pct"] == 0


def test_fills_happen_on_next_bar(candles):
    res = run_backtest(candles, fixed_strategy=TrendFollowing())
    sig = TrendFollowing().generate(candles)
    first_buy = res.trades.iloc[0]["time"]
    pos = candles.index.get_loc(first_buy)
    assert sig.iloc[pos - 1] == 1.0 and (pos < 2 or sig.iloc[pos - 2] == 0.0)
    assert res.trades.iloc[0]["price"] == pytest.approx(candles["open"].iloc[pos])


def test_metrics_keys():
    res = run_backtest(synthetic_candles(300, seed=1))
    for k in ("total_return_pct", "max_drawdown_pct", "sharpe", "trades", "win_rate_pct", "buy_and_hold_return_pct"):
        assert k in res.metrics


def test_too_little_data():
    with pytest.raises(ValueError):
        run_backtest(synthetic_candles(1))
