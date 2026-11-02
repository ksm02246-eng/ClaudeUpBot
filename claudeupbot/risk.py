"""Wallet-only risk controls.

The bot must never borrow: no margin, no MTF, no short selling, no intraday
leverage. Every buy is paid in full from cash that is already in the wallet,
minus a buffer for charges, and never more than MAX_CAPITAL overall.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Upstox product codes. "D" = delivery (fully paid). "I" (intraday) and "MTF" use leverage.
ALLOWED_PRODUCT = "D"


class RiskViolation(Exception):
    """Raised when an order would break a wallet-only rule."""


@dataclass
class WalletGuard:
    max_capital: float
    cash_buffer_pct: float = 0.02
    max_position_pct: float = 0.25
    max_daily_loss_pct: float = 0.03

    def spendable_cash(self, available_cash: float, deployed_value: float) -> float:
        """Cash the bot may still spend right now."""
        wallet_room = max(available_cash, 0.0) * (1 - self.cash_buffer_pct)
        cap_room = max(self.max_capital - deployed_value, 0.0)
        return max(min(wallet_room, cap_room), 0.0)

    def max_buy_quantity(self, price: float, available_cash: float, deployed_value: float,
                         current_position_value: float = 0.0, cost_pct: float = 0.0) -> int:
        if price <= 0:
            return 0
        per_instrument_room = max(self.max_capital * self.max_position_pct - current_position_value, 0.0)
        budget = min(self.spendable_cash(available_cash, deployed_value), per_instrument_room)
        return max(int(math.floor(budget / (price * (1 + cost_pct)))), 0)

    def validate_order(self, *, side: str, quantity: int, price: float, product: str,
                       available_cash: float, held_quantity: int, deployed_value: float,
                       day_pnl: float = 0.0) -> None:
        if quantity <= 0:
            raise RiskViolation("quantity must be positive")
        if product != ALLOWED_PRODUCT:
            raise RiskViolation(f"product {product!r} uses leverage; only delivery ('D') is allowed")
        side = side.upper()
        if side == "SELL":
            if quantity > held_quantity:
                raise RiskViolation(f"cannot sell {quantity}, only {held_quantity} held (no short selling)")
            return
        if side != "BUY":
            raise RiskViolation(f"unknown side {side!r}")
        if day_pnl < -self.max_daily_loss_pct * self.max_capital:
            raise RiskViolation("daily loss limit reached; no new buys today")
        value = quantity * price
        if value > self.spendable_cash(available_cash, deployed_value) + 1e-9:
            raise RiskViolation(
                f"order value {value:.2f} exceeds spendable wallet cash "
                f"{self.spendable_cash(available_cash, deployed_value):.2f}"
            )
