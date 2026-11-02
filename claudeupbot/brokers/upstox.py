"""Minimal Upstox v2 REST client (https://upstox.com/developer/api-documentation).

Real orders are refused unless LIVE_TRADING=true. Only delivery ("D") product is
ever sent, so every buy is paid in full from the wallet.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote, urlencode

import pandas as pd
import requests

from ..risk import ALLOWED_PRODUCT
from .base import Broker, Holding, OrderResult

BASE_URL = "https://api.upstox.com/v2"
AUTH_URL = f"{BASE_URL}/login/authorization/dialog"


class UpstoxError(RuntimeError):
    pass


def login_url(api_key: str, redirect_uri: str) -> str:
    """URL to open in a browser; Upstox redirects back with ?code=... for exchange_code()."""
    return f"{AUTH_URL}?{urlencode({'response_type': 'code', 'client_id': api_key, 'redirect_uri': redirect_uri})}"


def exchange_code(code: str, api_key: str, api_secret: str, redirect_uri: str, timeout: float = 15) -> str:
    resp = requests.post(
        f"{BASE_URL}/login/authorization/token",
        data={"code": code, "client_id": api_key, "client_secret": api_secret,
              "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
        headers={"Accept": "application/json"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise UpstoxError(f"token exchange failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()["access_token"]


class UpstoxBroker(Broker):
    def __init__(self, access_token: str, live_trading: bool = False, session: requests.Session | None = None,
                 timeout: float = 15):
        if not access_token:
            raise UpstoxError("UPSTOX_ACCESS_TOKEN is not set")
        self.live_trading = live_trading
        self.paper = not live_trading
        self.timeout = timeout
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {access_token}", "Accept": "application/json"})

    def _get(self, path: str, **params):
        resp = self.s.get(f"{BASE_URL}{path}", params=params or None, timeout=self.timeout)
        if resp.status_code != 200:
            raise UpstoxError(f"GET {path} -> {resp.status_code} {resp.text[:200]}")
        return resp.json()["data"]

    # ---- account -------------------------------------------------------
    def available_cash(self) -> float:
        """Equity-segment cash available to trade.

        Note: Upstox's available_margin can include collateral from pledged
        holdings. MAX_CAPITAL in settings is the hard ceiling the bot respects
        on top of this, so set it to the cash you actually want to use.
        """
        data = self._get("/user/get-funds-and-margin", segment="SEC")
        return float(data["equity"]["available_margin"])

    def holdings(self) -> dict[str, Holding]:
        out: dict[str, Holding] = {}
        for row in self._get("/portfolio/long-term-holdings") or []:
            key, qty = row["instrument_token"], int(row["quantity"])
            if qty:
                out[key] = Holding(key, qty, float(row["average_price"]))
        # Delivery buys made today show up as positions until settlement.
        for row in self._get("/portfolio/short-term-positions") or []:
            if row.get("product") != ALLOWED_PRODUCT:
                continue
            key, qty = row["instrument_token"], int(row["quantity"])
            if qty:
                prev = out.get(key)
                total = qty + (prev.quantity if prev else 0)
                avg = float(row.get("average_price") or row.get("buy_price") or 0)
                out[key] = Holding(key, total, avg if not prev else (prev.avg_price * prev.quantity + avg * qty) / total)
        return out

    # ---- market data ---------------------------------------------------
    def candles(self, instrument_key: str, interval: str = "30minute", days: int = 60) -> pd.DataFrame:
        """Historical candles. interval: 1minute, 30minute, day, week, month."""
        to_d = date.today()
        from_d = to_d - timedelta(days=days)
        key = quote(instrument_key, safe="")
        rows = self._get(f"/historical-candle/{key}/{interval}/{to_d}/{from_d}")["candles"]
        if interval in ("1minute", "30minute"):
            try:
                rows = rows + self._get(f"/historical-candle/intraday/{key}/{interval}")["candles"]
            except UpstoxError:
                pass
        return candles_to_frame(rows)

    # ---- orders --------------------------------------------------------
    def place_market_order(self, instrument_key, side, quantity, ref_price, product="D", tag="claudeupbot"):
        if product != ALLOWED_PRODUCT:
            raise UpstoxError("only delivery product 'D' is allowed (wallet-only)")
        if not self.live_trading:
            raise UpstoxError("LIVE_TRADING is not enabled; refusing to send a real order")
        body = {
            "quantity": int(quantity), "product": product, "validity": "DAY", "price": 0, "tag": tag[:20],
            "instrument_token": instrument_key, "order_type": "MARKET", "transaction_type": side.upper(),
            "disclosed_quantity": 0, "trigger_price": 0, "is_amo": False,
        }
        resp = self.s.post(f"{BASE_URL}/order/place", json=body, timeout=self.timeout)
        if resp.status_code != 200:
            raise UpstoxError(f"order rejected: {resp.status_code} {resp.text[:200]}")
        oid = resp.json()["data"]["order_id"]
        return OrderResult(instrument_key, side.upper(), int(quantity), ref_price, oid, "submitted", False)


def candles_to_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"][: len(rows[0])]
                      if rows else ["timestamp", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df.set_index("timestamp")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is not None:
        df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)
