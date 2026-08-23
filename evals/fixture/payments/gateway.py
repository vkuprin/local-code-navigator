"""Payment gateway entry points."""


def charge(account_id: str, cents: int) -> str:
    """Charge an account and return a transaction id."""
    if cents <= 0:
        raise ValueError("cents must be positive")
    return f"txn-{account_id}-{cents}"


def refund(transaction_id: str) -> bool:
    return transaction_id.startswith("txn-")
