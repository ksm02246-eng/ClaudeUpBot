"""Paper broker: simulates fills at the reference price and persists state to JSON."""

from __future__ import annotations

import json
import os
import uuid

from .base import Broker, Holding, OrderResult


class PaperBroker(Broker):
    paper = True

    def __init__(self, state_path: str | None = None, starting_cash: float = 50_000.0, cost_pct: float = 0.0012):
        self.state_path = state_path
        self.cost_pct = cost_pct
        self.cash = starting_cash
        self._holdings: dict[str, Holding] = {}
        if state_path and os.path.exists(state_path):
            with open(state_path) as fh:
                state = json.load(fh)
            self.cash = state["cash"]
            self._holdings = {k: Holding(k, v["quantity"], v["avg_price"]) for k, v in state["holdings"].items()}

    def _save(self) -> None:
        if not self.state_path:
            return
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with open(self.state_path, "w") as fh:
            json.dump({"cash": self.cash, "holdings": {k: {"quantity": h.quantity, "avg_price": h.avg_price}
                                                        for k, h in self._holdings.items()}}, fh, indent=2)

    def available_cash(self) -> float:
        return self.cash

    def holdings(self) -> dict[str, Holding]:
        return dict(self._holdings)

    def place_market_order(self, instrument_key, side, quantity, ref_price, product="D", tag="claudeupbot"):
        side = side.upper()
        h = self._holdings.get(instrument_key, Holding(instrument_key, 0, 0.0))
        if side == "BUY":
            cost = quantity * ref_price * (1 + self.cost_pct)
            if cost > self.cash + 1e-9:
                raise ValueError("paper broker: insufficient cash")
            self.cash -= cost
            new_qty = h.quantity + quantity
            h = Holding(instrument_key, new_qty, (h.avg_price * h.quantity + ref_price * quantity) / new_qty)
        else:
            if quantity > h.quantity:
                raise ValueError("paper broker: cannot sell more than held")
            self.cash += quantity * ref_price * (1 - self.cost_pct)
            h = Holding(instrument_key, h.quantity - quantity, h.avg_price)
        if h.quantity:
            self._holdings[instrument_key] = h
        else:
            self._holdings.pop(instrument_key, None)
        self._save()
        return OrderResult(instrument_key, side, quantity, ref_price, f"paper-{uuid.uuid4().hex[:10]}", "filled", True)
