from __future__ import annotations

from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal

from trading_base.constants import Precision


def compute_loss_cap(equity: Decimal, cap_pct: Decimal) -> Decimal:
    return (equity * cap_pct).quantize(Precision.IBKR_AMOUNT, rounding=ROUND_HALF_EVEN)


def compute_position_size(
    equity: Decimal,
    risk_pct: Decimal,
    stop_distance: Decimal,
    point_value: Decimal,
) -> int:
    """Return integer units (contracts or shares). Returns 0 if < 1 unit."""
    if stop_distance <= 0 or point_value <= 0:
        return 0
    risk_dollars = equity * risk_pct
    cost_per_unit = stop_distance * point_value
    result = (risk_dollars / cost_per_unit).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    return max(0, int(result))


def compute_gross_pnl(
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: int,
    point_value: Decimal,
) -> Decimal:
    return ((exit_price - entry_price) * quantity * point_value).quantize(
        Precision.AMOUNT, rounding=ROUND_HALF_EVEN
    )


def compute_target_price(
    entry_price: Decimal,
    stop_price: Decimal,
    rr_ratio: Decimal,
) -> Decimal:
    """Compute target for a long position: entry + (entry - stop) × rr_ratio."""
    return (entry_price + (entry_price - stop_price) * rr_ratio).quantize(
        Precision.PRICE, rounding=ROUND_HALF_EVEN
    )
