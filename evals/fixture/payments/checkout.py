"""Checkout flow. Calls the real gateway charge."""

from payments.gateway import charge


def complete_order(account_id: str, total_cents: int) -> str:
    return charge(account_id, total_cents)


def complete_subscription(account_id: str, monthly_cents: int) -> str:
    first = charge(account_id, monthly_cents)
    return first
