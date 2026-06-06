from __future__ import annotations

import argparse
import sys

from trading_base.constants import TradingMode

_LIVE_WARNING = (
    "WARNING: --mode live selected. Real money at risk. "
    "Ensure paper trading validation is complete before proceeding."
)


def parse_mode(argv: list[str] | None = None) -> TradingMode:
    parser = argparse.ArgumentParser(description="Trading system mode selector")
    parser.add_argument(
        "--mode",
        required=True,
        choices=[m.value for m in TradingMode],
        help="Trading mode: dev | paper | live",
    )
    args = parser.parse_args(argv)
    mode = TradingMode(args.mode)
    if mode == TradingMode.LIVE:
        print(_LIVE_WARNING, file=sys.stderr)
    return mode
