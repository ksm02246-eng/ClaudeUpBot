import pytest

from claudeupbot.risk import RiskViolation, WalletGuard

G = WalletGuard(max_capital=10_000, cash_buffer_pct=0.02, max_position_pct=0.5, max_daily_loss_pct=0.03)


def test_cannot_spend_more_than_wallet():
    with pytest.raises(RiskViolation):
        G.validate_order(side="BUY", quantity=10, price=100, product="D", available_cash=500,
                         held_quantity=0, deployed_value=0)


def test_capital_cap_applies_even_with_more_cash():
    assert G.spendable_cash(available_cash=1_000_000, deployed_value=9_000) == pytest.approx(1_000)


def test_leveraged_products_rejected():
    for product in ("I", "MTF", "CO"):
        with pytest.raises(RiskViolation):
            G.validate_order(side="BUY", quantity=1, price=10, product=product, available_cash=10_000,
                             held_quantity=0, deployed_value=0)


def test_no_short_selling():
    with pytest.raises(RiskViolation):
        G.validate_order(side="SELL", quantity=5, price=10, product="D", available_cash=0,
                         held_quantity=3, deployed_value=0)


def test_daily_loss_blocks_buys_not_sells():
    with pytest.raises(RiskViolation):
        G.validate_order(side="BUY", quantity=1, price=10, product="D", available_cash=10_000,
                         held_quantity=0, deployed_value=0, day_pnl=-500)
    G.validate_order(side="SELL", quantity=1, price=10, product="D", available_cash=0,
                     held_quantity=1, deployed_value=10, day_pnl=-500)


def test_max_buy_quantity_respects_all_limits():
    # wallet 3000*0.98=2940, cap room 10000, per-instrument 5000 -> 2940/100 = 29
    assert G.max_buy_quantity(100, available_cash=3_000, deployed_value=0) == 29
    # per-instrument cap: 5000 - 4000 already held = 1000 -> 10
    assert G.max_buy_quantity(100, available_cash=100_000, deployed_value=4_000, current_position_value=4_000) == 10
