from datetime import timedelta

from sooner.core.policy import load_clinics
from sooner.tests.conftest import T0, make_request


def test_soonest_slot_per_clinic():
    c = load_clinics()
    r = make_request()
    assert c["clinic_downtown"].soonest_slot(r).slot_id == "dt-1"
    assert c["clinic_bayside"].soonest_slot(r).slot_id == "bs-1"


def test_no_matching_slot_returns_none():
    c = load_clinics()["clinic_downtown"]
    assert c.soonest_slot(make_request(specialty="cardiology")) is None
    assert c.soonest_slot(make_request(insurance="Kaiser")) is None
    assert c.soonest_slot(make_request(time_window={"start": T0 - timedelta(days=9), "end": T0 - timedelta(days=8)})) is None


def test_radius_excludes_far_clinic():
    assert not load_clinics()["clinic_northgate"].matches(make_request(radius_miles=5, insurance="Cigna"))


def test_deposit_follows_policy():
    c = load_clinics()["clinic_bayside"]
    slot = c.slots[0]
    assert c.price_and_deposit(slot) == (220, 22.0) and slot.deposit == 22.0


def test_max_deposit_filters_slots():
    c = load_clinics()["clinic_downtown"]
    assert c.soonest_slot(make_request(max_deposit=5)) is None
