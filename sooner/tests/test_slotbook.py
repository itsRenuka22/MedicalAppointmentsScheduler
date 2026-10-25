import pytest

from sooner.core.slotbook import BOOKED, HELD, OPEN, SlotBook
from sooner.core.store import MemoryStore


@pytest.fixture
def book():
    b = SlotBook(MemoryStore(), "c1")
    b.add("s1", "2026-10-26T09:00:00", 100, 10)
    return b


def test_hold_increments_version(book):
    assert book.try_hold("s1", 0) == (True, 1, HELD)
    assert book.get("s1")["state"] == HELD


def test_second_hold_with_same_version_loses(book):
    assert book.try_hold("s1", 0)[0] is True
    assert book.try_hold("s1", 0) == (False, 1, "slot_taken")


def test_stale_version_rejected_after_release(book):
    book.try_hold("s1", 0); book.release("s1")
    assert book.try_hold("s1", 0)[0] is False
    assert book.try_hold("s1", book.get("s1")["version"])[0] is True


def test_confirm_requires_hold_and_free_reopens(book):
    assert book.confirm("s1") is False
    book.try_hold("s1", 0)
    assert book.confirm("s1") and book.get("s1")["state"] == BOOKED
    assert book.free("s1") and book.get("s1")["state"] == OPEN


def test_unknown_slot_and_remove_only_when_open(book):
    assert book.try_hold("nope", 0)[0] is False
    book.try_hold("s1", 0)
    assert book.remove("s1") is False
    book.release("s1")
    assert book.remove("s1") is True and book.get("s1") is None


def test_slots_isolated_per_clinic():
    store = MemoryStore()
    a, b = SlotBook(store, "a"), SlotBook(store, "b")
    a.add("s", "2026-10-26T09:00:00", 1, 1)
    assert b.get("s") is None
