"""Escrow state machine: hold, release, refund. Release/refund are idempotent."""
import itertools

HELD, RELEASED, REFUNDED = "held", "released", "refunded"


class EscrowError(Exception):
    pass


class Escrow:
    def __init__(self):
        self._state: dict[str, tuple[float, str]] = {}
        self._ids = itertools.count(1)

    def hold(self, amount: float) -> str:
        if amount <= 0:
            raise EscrowError("amount must be positive")
        escrow_id = f"esc-{next(self._ids)}"
        self._state[escrow_id] = (amount, HELD)
        return escrow_id

    def _get(self, escrow_id: str) -> tuple[float, str]:
        if escrow_id not in self._state:
            raise EscrowError(f"unknown escrow {escrow_id}")
        return self._state[escrow_id]

    def status(self, escrow_id: str) -> str:
        return self._get(escrow_id)[1]

    def release(self, escrow_id: str) -> str:
        amount, st = self._get(escrow_id)
        if st == REFUNDED:
            raise EscrowError("cannot release a refunded escrow")
        self._state[escrow_id] = (amount, RELEASED)
        return RELEASED

    def refund(self, escrow_id: str) -> str:
        amount, st = self._get(escrow_id)
        if st == RELEASED:
            raise EscrowError("cannot refund a released escrow")
        self._state[escrow_id] = (amount, REFUNDED)
        return REFUNDED
