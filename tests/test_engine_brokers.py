from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from claudeupbot.brokers import PaperBroker, UpstoxBroker, UpstoxError
from claudeupbot.brokers.upstox import candles_to_frame
from claudeupbot.config import Settings
from claudeupbot.engine import Engine, Journal, is_market_open
from claudeupbot.scheduler import seconds_until_next_run

IST = ZoneInfo("Asia/Kolkata")


def _settings(**kw):
    base = dict(instruments=["NSE_EQ|TEST"], max_capital=20_000, max_position_pct=0.5)
    base.update(kw)
    return Settings(**base)


def test_engine_paper_cycle(tmp_path, candles):
    broker = PaperBroker(str(tmp_path / "state.json"), starting_cash=20_000)
    eng = Engine(_settings(), broker, lambda k: candles, journal=Journal(str(tmp_path / "j.jsonl")))
    decisions = eng.run_once(datetime(2024, 5, 2, 11, 0, tzinfo=IST))
    assert len(decisions) == 1
    d = decisions[0]
    assert d.action in {"BUY", "SELL", "HOLD", "SKIP"}
    assert broker.available_cash() >= 0
    assert (tmp_path / "j.jsonl").read_text().strip()


def test_engine_buys_within_wallet(tmp_path, candles):
    # find a cut where trend following is long and the regime is bullish
    from claudeupbot.regime import classify_series
    from claudeupbot.strategies import TrendFollowing

    regimes = classify_series(candles)
    sig = TrendFollowing().generate(candles)
    cut = next(i for i in range(150, len(candles)) if regimes.iloc[i] == "bullish" and sig.iloc[i] == 1.0)
    df = candles.iloc[: cut + 1]
    broker = PaperBroker(None, starting_cash=3_000)
    eng = Engine(_settings(), broker, lambda k: df, journal=Journal(None))
    d = eng.run_once(datetime(2024, 5, 2, 11, 0, tzinfo=IST))[0]
    assert d.action == "BUY"
    assert broker.available_cash() >= 0
    assert d.quantity * d.price <= 3_000


def test_engine_skips_short_history(tmp_path, candles):
    eng = Engine(_settings(), PaperBroker(None, 10_000), lambda k: candles.iloc[:50], journal=Journal(None))
    assert eng.run_once(datetime(2024, 5, 2, 11, 0, tzinfo=IST))[0].action == "SKIP"


def test_engine_survives_data_errors(candles):
    def bad(_):
        raise requests.ConnectionError("blocked")

    eng = Engine(_settings(), PaperBroker(None, 10_000), bad, journal=Journal(None))
    assert eng.run_once(datetime(2024, 5, 2, 11, 0, tzinfo=IST)) == []


def test_upstox_refuses_orders_without_live_flag():
    b = UpstoxBroker("dummy-token", live_trading=False)
    with pytest.raises(UpstoxError):
        b.place_market_order("NSE_EQ|X", "BUY", 1, 100.0)
    with pytest.raises(UpstoxError):
        UpstoxBroker("dummy-token", live_trading=True).place_market_order("NSE_EQ|X", "BUY", 1, 100.0, product="I")


def test_upstox_requires_token():
    with pytest.raises(UpstoxError):
        UpstoxBroker("")


def test_candles_to_frame():
    rows = [["2024-05-02T09:45:00+05:30", 10, 11, 9, 10.5, 1000, 0],
            ["2024-05-02T09:15:00+05:30", 9, 10, 8, 9.5, 900, 0]]
    df = candles_to_frame(rows)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index[0].hour == 9 and df.index[0].minute == 15


def test_market_hours():
    assert is_market_open(datetime(2024, 5, 2, 10, 0, tzinfo=IST))
    assert not is_market_open(datetime(2024, 5, 4, 10, 0, tzinfo=IST))  # Saturday
    assert not is_market_open(datetime(2024, 5, 2, 16, 0, tzinfo=IST))


def test_scheduler_alignment():
    secs = seconds_until_next_run(datetime(2024, 5, 2, 10, 7, 0, tzinfo=IST), 15)
    assert secs == pytest.approx(8 * 60 + 5)


def test_live_flag_parsing(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "yes")
    assert Settings.from_env().live_trading is False
    monkeypatch.setenv("LIVE_TRADING", "true")
    assert Settings.from_env().live_trading is True
