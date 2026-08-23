"""A self-contained ledger. Answerable by reading this one file."""

OPENING_BALANCE_CENTS = 25_000
MONTHLY_FEE_CENTS = 1_200
PROMO_DISCOUNT_CENTS = 200


def closing_balance(months: int) -> int:
    """Balance after `months` months of fees, with the promo applied every third month."""
    balance = OPENING_BALANCE_CENTS
    for month in range(1, months + 1):
        balance -= MONTHLY_FEE_CENTS
        if month % 3 == 0:
            balance += PROMO_DISCOUNT_CENTS
    return balance
