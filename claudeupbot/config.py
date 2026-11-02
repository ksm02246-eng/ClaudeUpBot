"""Settings loaded from environment variables (optionally via a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _list(name: str, default: str) -> list[str]:
    raw = os.getenv(name) or default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = ""
    upstox_access_token: str = ""

    live_trading: bool = False
    max_capital: float = 50_000.0
    cash_buffer_pct: float = 0.02
    max_position_pct: float = 0.25
    max_daily_loss_pct: float = 0.03

    instruments: list[str] = field(default_factory=list)
    candle_interval: str = "30minute"
    run_every_minutes: int = 15

    journal_path: str = "data/journal.jsonl"
    paper_state_path: str = "data/state_paper.json"
    paper_starting_cash: float = 50_000.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            upstox_api_key=os.getenv("UPSTOX_API_KEY", ""),
            upstox_api_secret=os.getenv("UPSTOX_API_SECRET", ""),
            upstox_redirect_uri=os.getenv("UPSTOX_REDIRECT_URI", ""),
            upstox_access_token=os.getenv("UPSTOX_ACCESS_TOKEN", ""),
            # Only the exact string "true" enables live orders.
            live_trading=os.getenv("LIVE_TRADING", "false").strip().lower() == "true",
            max_capital=_float("MAX_CAPITAL", 50_000.0),
            cash_buffer_pct=_float("CASH_BUFFER_PCT", 0.02),
            max_position_pct=_float("MAX_POSITION_PCT", 0.25),
            max_daily_loss_pct=_float("MAX_DAILY_LOSS_PCT", 0.03),
            instruments=_list("INSTRUMENTS", "NSE_EQ|INE002A01018"),
            candle_interval=os.getenv("CANDLE_INTERVAL", "30minute"),
            run_every_minutes=_int("RUN_EVERY_MINUTES", 15),
            journal_path=os.getenv("JOURNAL_PATH", "data/journal.jsonl"),
            paper_state_path=os.getenv("PAPER_STATE_PATH", "data/state_paper.json"),
            paper_starting_cash=_float("PAPER_STARTING_CASH", 50_000.0),
        )

    def missing_live_credentials(self) -> list[str]:
        """Names of env vars that must be set before talking to Upstox."""
        missing = []
        if not self.upstox_access_token:
            missing.append("UPSTOX_ACCESS_TOKEN")
        return missing
