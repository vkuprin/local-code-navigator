"""Deprecated billing path.

Defines a method also named `charge`. It is unrelated to payments.gateway.charge and
must not be reported as a reference to it.
"""


class LegacyBiller:
    def charge(self, amount: int) -> str:
        """A different charge entirely -- same name, no relationship."""
        return f"legacy-{amount}"


def run_legacy(amount: int) -> str:
    biller = LegacyBiller()
    return biller.charge(amount)
