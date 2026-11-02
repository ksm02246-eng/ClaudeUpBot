"""Command line entry point: `python -m claudeupbot <command>`."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .backtest import run_backtest
from .config import Settings
from .data import load_csv, synthetic_candles
from .strategies import ALL_STRATEGIES


def _cmd_backtest(args) -> int:
    df = load_csv(args.csv) if args.csv else synthetic_candles(n_days=args.days, seed=args.seed)
    fixed = None if args.strategy == "auto" else ALL_STRATEGIES[args.strategy]()
    res = run_backtest(df, initial_cash=args.cash, fixed_strategy=fixed)
    print(json.dumps(res.metrics, indent=2))
    print("\nRegime mix (% of bars):")
    print((res.regimes.value_counts(normalize=True) * 100).round(1).to_string())
    if args.trades and not res.trades.empty:
        print("\n" + res.trades.to_string(index=False))
    return 0


def _build_engine(settings: Settings):
    from .brokers import PaperBroker, UpstoxBroker
    from .engine import Engine, Journal

    missing = settings.missing_live_credentials()
    if missing:
        raise SystemExit(f"Missing settings: {', '.join(missing)}. Add them to .env (see .env.example).")
    upstox = UpstoxBroker(settings.upstox_access_token, live_trading=settings.live_trading)
    broker = upstox if settings.live_trading else PaperBroker(settings.paper_state_path, settings.paper_starting_cash)
    data_fn = lambda key: upstox.candles(key, settings.candle_interval)  # noqa: E731
    return Engine(settings, broker, data_fn, journal=Journal(settings.journal_path),
                  day_state_path=settings.paper_state_path.replace(".json", "_day.json"))


def _cmd_run_once(args) -> int:
    settings = Settings.from_env()
    engine = _build_engine(settings)
    for d in engine.run_once():
        print(json.dumps(d.__dict__, default=str))
    return 0


def _cmd_run(args) -> int:
    from .scheduler import run_forever

    settings = Settings.from_env()
    engine = _build_engine(settings)
    mode = "LIVE" if settings.live_trading else "PAPER"
    logging.info("ClaudeUpBot running in %s mode every %s min", mode, settings.run_every_minutes)
    run_forever(engine, settings.run_every_minutes)
    return 0


def _cmd_check(args) -> int:
    s = Settings.from_env()
    print(f"mode: {'LIVE' if s.live_trading else 'PAPER'}")
    print(f"instruments: {s.instruments}")
    print(f"max capital: {s.max_capital}  position cap: {s.max_position_pct:.0%}  buffer: {s.cash_buffer_pct:.0%}")
    missing = s.missing_live_credentials()
    print("credentials: " + ("OK" if not missing else "missing " + ", ".join(missing)))
    if not missing:
        from .brokers import UpstoxBroker

        try:
            print(f"wallet cash: {UpstoxBroker(s.upstox_access_token).available_cash():.2f}")
        except Exception as exc:  # noqa: BLE001
            print(f"upstox: {exc}")
            return 1
    return 0 if not missing else 1


def _cmd_login_url(args) -> int:
    from .brokers.upstox import login_url

    s = Settings.from_env()
    if not s.upstox_api_key or not s.upstox_redirect_uri:
        raise SystemExit("Set UPSTOX_API_KEY and UPSTOX_REDIRECT_URI first.")
    print(login_url(s.upstox_api_key, s.upstox_redirect_uri))
    return 0


def _cmd_exchange_code(args) -> int:
    from .brokers.upstox import exchange_code

    s = Settings.from_env()
    token = exchange_code(args.code, s.upstox_api_key, s.upstox_api_secret, s.upstox_redirect_uri)
    print("Put this in UPSTOX_ACCESS_TOKEN (valid until ~03:30 IST tomorrow):")
    print(token)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="claudeupbot")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", help="backtest on a CSV or synthetic data")
    b.add_argument("--csv", help="CSV with timestamp,open,high,low,close,volume")
    b.add_argument("--strategy", default="auto", choices=["auto", *ALL_STRATEGIES])
    b.add_argument("--cash", type=float, default=100_000)
    b.add_argument("--days", type=int, default=750)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--trades", action="store_true", help="print the trade list")
    b.set_defaults(func=_cmd_backtest)

    sub.add_parser("check", help="show config and test the Upstox connection").set_defaults(func=_cmd_check)
    sub.add_parser("run-once", help="run a single trading cycle").set_defaults(func=_cmd_run_once)
    sub.add_parser("run", help="run every RUN_EVERY_MINUTES during market hours").set_defaults(func=_cmd_run)
    sub.add_parser("login-url", help="print the Upstox login URL").set_defaults(func=_cmd_login_url)
    e = sub.add_parser("exchange-code", help="turn the ?code= from the login redirect into an access token")
    e.add_argument("code")
    e.set_defaults(func=_cmd_exchange_code)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
