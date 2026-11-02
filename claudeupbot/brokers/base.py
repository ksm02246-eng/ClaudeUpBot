from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Holding:
    instrument_key: str
    quantity: int
    avg_price: float


@dataclass
class OrderResult:
    instrument_key: str
    side: str
    quantity: int
    price: float
    order_id: str
    status: str
    paper: bool


class Broker(ABC):
    paper: bool = True

    @abstractmethod
    def available_cash(self) -> float: ...

    @abstractmethod
    def holdings(self) -> dict[str, Holding]: ...

    @abstractmethod
    def place_market_order(self, instrument_key: str, side: str, quantity: int, ref_price: float,
                           product: str = "D", tag: str = "claudeupbot") -> OrderResult: ...
