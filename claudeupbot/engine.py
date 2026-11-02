"""One trading cycle: data -> regime -> strategy -> wallet guard -> order -> journal."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from .brokers.base import Broker
from .config import Settings
from .regime import current_regime
from .risk import ALLOWED_PRODUCT, RiskViolation, WalletGuard
from .selector import MARKET_CLOSE, MARKET_OPEN, StrategySelector, entries_allowed

IST = ZoneInfo("Asia/Kolkata")
MIN_BARS = 120

DataFn = Callable[[str], pd.DataFrame]


def now_ist() -> datetime:
    return datetime.now(IST)


def is_market_open(ts: datetime) -> bool:
    """NSE cash session, Mon-Fri. Exchange holidays are not modelled; orders on a
    holiday are simply rejected by the broker."""
    ts = ts.astimezone(IST) if ts.tzinfo else ts
    return ts.weekday() < 5 and MARKET_OPEN <= ts.time() <= MARKET_CLOSE


@dataclass
class Decision:
    instrument_key: str
    regime: str
    strategy: str
    target_exposure: float
    price: float
    held_qty: int
    action: str  # BUY / SELL / HOLD / SKIP / ERROR
    quantity: int = 0
    note: str = ""
    order_id: str = ""


class Journal:
    def __init__(self, path: str | None):
        self.path = path

    def write(self, record: dict) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")


class Engine:
    def __init__(self, settings: Settings, broker: Broker, data_fn: DataFn,
                 selector: StrategySelector | None = None, journal: Journal | None = None,
                 day_state_path: str | None = None):
        self.s = settings
        self.broker = broker
        self.data_fn = data_fn
        self.selector = selector or StrategySelector()
        self.journal = journal or Journal(settings.journal_path)
        self.day_state_path = day_state_path
        self.guard = WalletGuard(settings.max_capital, settings.cash_buffer_pct,
                                 settings.max_position_pct, settings.max_daily_loss_pct)

    # -- day P&L tracking for the daily loss limit ----------------------
    def _day_pnl(self, ts: datetime, equity: float) -> float:
        if not self.day_state_path:
            return 0.0
        today = ts.date().isoformat()
        state = {}
        if os.path.exists(self.day_state_path):
            with open(self.day_state_path) as fh:
                state = json.load(fh)
        if state.get("date") != today:
            state = {"date": today, "start_equity": equity}
            os.makedirs(os.path.dirname(self.day_state_path) or ".", exist_ok=True)
            with open(self.day_state_path, "w") as fh:
                json.dump(state, fh)
        return equity - float(state["start_equity"])

    def run_once(self, ts: datetime | None = None) -> list[Decision]:
        ts = ts or now_ist()
        bar_ts = pd.Timestamp(ts.replace(tzinfo=None))
        frames: dict[str, pd.DataFrame] = {}
        for key in self.s.instruments:
            try:
                frames[key] = self.data_fn(key)
            except Exception as exc:  # noqa: BLE001 - one bad instrument must not stop the cycle
                frames[key] = None
                self._log(ts, Decision(key, "", "", 0.0, 0.0, 0, "ERROR", note=f"data: {exc}"))

        holdings = self.broker.holdings()
        last_price = {k: float(df["close"].iloc[-1]) for k, df in frames.items() if df is not None and len(df)}
        deployed = sum(h.quantity * last_price.get(k, h.avg_price) for k, h in holdings.items())
        cash = self.broker.available_cash()
        day_pnl = self._day_pnl(ts, cash + deployed)

        decisions = []
        for key, df in frames.items():
            if df is None:
                continue
            decisions.append(self._decide_and_act(key, df, ts, bar_ts, holdings, day_pnl))
            # refresh balances after each order so later instruments see the real wallet
            holdings = self.broker.holdings()
            deployed = sum(h.quantity * last_price.get(k, h.avg_price) for k, h in holdings.items())
        return decisions

    def _decide_and_act(self, key, df, ts, bar_ts, holdings, day_pnl) -> Decision:
        held = holdings.get(key).quantity if key in holdings else 0
        if len(df) < MIN_BARS:
            d = Decision(key, "unknown", "", 0.0, float(df["close"].iloc[-1]) if len(df) else 0.0, held,
                         "SKIP", note=f"only {len(df)} candles, need {MIN_BARS}")
            self._log(ts, d)
            return d

        regime = current_regime(df)
        strategy = self.selector.select(regime, bar_ts)
        target = strategy.latest(df)
        price = float(df["close"].iloc[-1])
        d = Decision(key, regime.value, strategy.name, target, price, held, "HOLD")

        per_instrument_budget = self.s.max_capital * self.s.max_position_pct
        target_qty = int(math.floor(target * per_instrument_budget / price)) if target > 0 else 0

        try:
            if target_qty < held:
                d.action, d.quantity = "SELL", held - target_qty
            elif target_qty > held:
                if not entries_allowed(bar_ts):
                    d.note = "outside entry window"
                else:
                    current_value = held * price
                    deployed = sum(h.quantity * h.avg_price for h in holdings.values())
                    room = self.guard.max_buy_quantity(price, self.broker.available_cash(), deployed,
                                                       current_value, cost_pct=0.0012)
                    qty = min(target_qty - held, room)
                    if qty > 0:
                        d.action, d.quantity = "BUY", qty
                    else:
                        d.note = "no spendable wallet cash"
            if d.action in ("BUY", "SELL"):
                deployed = sum(h.quantity * h.avg_price for h in holdings.values())
                self.guard.validate_order(side=d.action, quantity=d.quantity, price=price, product=ALLOWED_PRODUCT,
                                          available_cash=self.broker.available_cash(), held_quantity=held,
                                          deployed_value=deployed, day_pnl=day_pnl)
                res = self.broker.place_market_order(key, d.action, d.quantity, price, product=ALLOWED_PRODUCT)
                d.order_id = res.order_id
                d.note = (d.note + " paper" if res.paper else d.note + " live").strip()
        except RiskViolation as exc:
            d.action, d.note = "SKIP", f"risk: {exc}"
        except Exception as exc:  # noqa: BLE001
            d.action, d.note = "ERROR", str(exc)
        self._log(ts, d)
        return d

    def _log(self, ts, d: Decision) -> None:
        self.journal.write({"time": ts.isoformat(), **d.__dict__})
