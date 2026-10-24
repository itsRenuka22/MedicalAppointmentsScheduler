from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from sooner.core.slots import BOOKED, HELD, OPEN, Slot, confirm, release, try_hold


def mk():
    return Slot("s1", datetime(2026, 10, 26, 9), 100, 10)


def test_hold_open_slot_increments_version():
    s = mk()
    assert try_hold(s, 0) == (True, 1, "held")
    assert s.state == HELD and s.version == 1


def test_two_holds_only_one_wins():
    s = mk()
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda _: try_hold(s, 0), range(50)))
    assert sum(r[0] for r in results) == 1


def test_hold_on_held_slot_rejected():
    s = mk()
    try_hold(s, 0)
    assert try_hold(s, 1) == (False, 1, "slot_taken")


def test_stale_version_rejected():
    s = mk()
    try_hold(s, 0); release(s)
    assert try_hold(s, 0)[0] is False


def test_released_slot_can_be_held_again():
    s = mk()
    try_hold(s, 0); release(s)
    assert s.state == OPEN
    assert try_hold(s, s.version)[0] is True


def test_confirm_requires_hold():
    s = mk()
    assert confirm(s) is False
    try_hold(s, 0)
    assert confirm(s) and s.state == BOOKED
