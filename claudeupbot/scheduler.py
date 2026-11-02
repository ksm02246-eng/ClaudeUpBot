"""Run the engine on its own during market hours."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from .engine import IST, Engine, is_market_open, now_ist

log = logging.getLogger("claudeupbot.scheduler")


def seconds_until_next_run(now: datetime, every_minutes: int) -> float:
    """Align runs to wall-clock multiples of every_minutes (e.g. :00, :15, :30, :45)."""
    now = now.astimezone(IST)
    minute_block = (now.minute // every_minutes + 1) * every_minutes
    nxt = now.replace(second=5, microsecond=0) + timedelta(minutes=minute_block - now.minute)
    return max((nxt - now).total_seconds(), 1.0)


def run_forever(engine: Engine, every_minutes: int, max_cycles: int | None = None) -> None:
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        now = now_ist()
        if is_market_open(now):
            try:
                for d in engine.run_once(now):
                    log.info("%s %s %s %s qty=%s %s", d.instrument_key, d.regime, d.strategy, d.action,
                             d.quantity, d.note)
            except Exception:  # noqa: BLE001 - keep the loop alive
                log.exception("cycle failed")
        else:
            log.debug("market closed at %s", now)
        cycles += 1
        time.sleep(seconds_until_next_run(now_ist(), every_minutes))
