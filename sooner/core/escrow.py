"""Escrow state machine: hold, release, refund. Release/refund are idempotent."""
from typing import Optional

from sooner.core.store import MemoryStore, Store

HELD, RELEASED, REFUNDED = "held", "released", "refunded"


class EscrowError(Exception):
    pass


class Escrow:
    def __init__(self, store: Optional[Store] = None):
        self.store = store if store is not None else MemoryStore()

    @property
    def _state(self) -> dict:
        return {k: tuple(v) for k, v in self.store.get("escrow", {}).items()}

    def _put(self, escrow_id: str, amount: float, state: str) -> None:
        ledger = self.store.get("escrow", {})
        ledger[escrow_id] = [amount, state]
        self.store.set("escrow", ledger)

    def hold(self, amount: float) -> str:
        if amount <= 0:
            raise EscrowError("amount must be positive")
        n = self.store.get("escrow_n", 0) + 1
        self.store.set("escrow_n", n)
        escrow_id = f"esc-{n}"
        self._put(escrow_id, amount, HELD)
        return escrow_id

    def _get(self, escrow_id: str) -> tuple[float, str]:
        entry = self.store.get("escrow", {}).get(escrow_id)
        if entry is None:
            raise EscrowError(f"unknown escrow {escrow_id}")
        return entry[0], entry[1]

    def status(self, escrow_id: str) -> str:
        return self._get(escrow_id)[1]

    def release(self, escrow_id: str) -> str:
        amount, st = self._get(escrow_id)
        if st == REFUNDED:
            raise EscrowError("cannot release a refunded escrow")
        self._put(escrow_id, amount, RELEASED)
        return RELEASED

    def refund(self, escrow_id: str) -> str:
        amount, st = self._get(escrow_id)
        if st == RELEASED:
            raise EscrowError("cannot refund a released escrow")
        self._put(escrow_id, amount, REFUNDED)
        return REFUNDED
