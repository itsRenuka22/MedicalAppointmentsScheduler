"""Slot state machine with a compare-and-set optimistic lock."""
import threading
from dataclasses import dataclass, field
from datetime import datetime

OPEN, HELD, BOOKED = "open", "held", "booked"
_lock = threading.Lock()  # makes the compare-and-set atomic across threads


@dataclass
class Slot:
    slot_id: str
    time: datetime
    price: float
    deposit: float
    state: str = OPEN
    version: int = 0


def try_hold(slot: Slot, expected_version: int) -> tuple[bool, int, str]:
    """Move open -> held only if the version matches; otherwise slot_taken."""
    with _lock:
        if slot.state != OPEN or slot.version != expected_version:
            return False, slot.version, "slot_taken"
        slot.state = HELD
        slot.version += 1
        return True, slot.version, "held"


def confirm(slot: Slot) -> bool:
    with _lock:
        if slot.state != HELD:
            return False
        slot.state = BOOKED
        slot.version += 1
        return True


def release(slot: Slot) -> bool:
    with _lock:
        if slot.state != HELD:
            return False
        slot.state = OPEN
        slot.version += 1
        return True


def free(slot: Slot) -> bool:
    """A booked slot freed by a cancellation becomes open again."""
    with _lock:
        if slot.state == OPEN:
            return False
        slot.state = OPEN
        slot.version += 1
        return True
