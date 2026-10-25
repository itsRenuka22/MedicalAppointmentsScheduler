"""Store-backed slots with a compare-and-set hold (version numbers), per clinic."""
from typing import Optional

from sooner.core.store import Store

OPEN, HELD, BOOKED = "open", "held", "booked"


class SlotBook:
    def __init__(self, store: Store, clinic_id: str):
        self.store, self.key = store, f"slots:{clinic_id}"

    def _all(self) -> dict:
        return self.store.get(self.key, {})

    def all(self) -> dict:
        return self._all()

    def get(self, slot_id: str) -> Optional[dict]:
        return self._all().get(slot_id)

    def add(self, slot_id: str, time_iso: str, price: float, deposit: float) -> None:
        slots = self._all()
        slots[slot_id] = {"time": time_iso, "price": price, "deposit": deposit,
                          "state": OPEN, "version": 0}
        self.store.set(self.key, slots)

    def remove(self, slot_id: str) -> bool:
        slots = self._all()
        if slot_id not in slots or slots[slot_id]["state"] != OPEN:
            return False
        del slots[slot_id]
        self.store.set(self.key, slots)
        return True

    def _transition(self, slot_id: str, allowed: tuple, new_state: str, expected_version=None):
        slots = self._all()
        s = slots.get(slot_id)
        if s is None or s["state"] not in allowed:
            return False, (s or {}).get("version", -1), "slot_taken"
        if expected_version is not None and s["version"] != expected_version:
            return False, s["version"], "slot_taken"
        s["state"], s["version"] = new_state, s["version"] + 1
        self.store.set(self.key, slots)
        return True, s["version"], new_state

    def try_hold(self, slot_id: str, expected_version: int):
        """Compare-and-set: open -> held only if the version matches."""
        return self._transition(slot_id, (OPEN,), HELD, expected_version)

    def confirm(self, slot_id: str) -> bool:
        return self._transition(slot_id, (HELD,), BOOKED)[0]

    def release(self, slot_id: str) -> bool:
        return self._transition(slot_id, (HELD,), OPEN)[0]

    def free(self, slot_id: str) -> bool:
        """A booked slot freed by a cancellation becomes open again."""
        return self._transition(slot_id, (HELD, BOOKED), OPEN)[0]
