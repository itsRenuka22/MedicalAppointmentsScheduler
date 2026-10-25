from datetime import datetime

import pytest

from sooner.core.clinic_host import ClinicHost
from sooner.core.store import MemoryStore
from sooner.shared.models import BookingRequest
from sooner.tests.conftest import make_request

NOW = datetime(2026, 10, 25, 8, 0)


def profile(cid, name="Clinic", specialties=("dermatology",), owner="", slots=None, **kw):
    p = dict(clinic_id=cid, name=name, address="1 Main St", lat=37.7946, lng=-122.395,
             specialties=list(specialties), insurance=["Aetna"], deposit_pct=0.1, owner=owner,
             slots=slots or [{"slot_id": f"{cid}-1", "time": "2026-10-26T09:00:00", "price": 100}])
    p.update(kw)
    return p


@pytest.fixture
def host():
    h = ClinicHost(MemoryStore())
    h.add_clinic(profile("a", "Alpha"))
    h.add_clinic(profile("b", "Beta", slots=[{"slot_id": "b-1", "time": "2026-10-26T08:00:00", "price": 200}]))
    return h


def test_routing_by_clinic_id(host):
    both = host.offers_for(make_request(), now=NOW)
    assert {o.clinic_id for o in both} == {"a", "b"}
    only_b = host.offers_for(make_request(clinic_ids=["b"]), now=NOW)
    assert [o.clinic_id for o in only_b] == ["b"]
    assert host.offers_for(make_request(clinic_ids=["zzz"]), now=NOW) == []


def test_booking_routes_to_the_right_clinic(host):
    o = host.offers_for(make_request(clinic_ids=["b"]), now=NOW)[0]
    r = host.book(BookingRequest(request_id="r", clinic_id="b", slot_id=o.slot_id,
                                 patient_address="p", expected_version=o.slot_version))
    assert r.ok and r.confirmation_id
    assert host.slots("a").get("a-1")["state"] == "open"
    assert host.slots("b").get("b-1")["state"] == "booked"


def test_booking_unknown_clinic_or_slot_fails_cleanly(host):
    for cid, sid in [("zzz", "a-1"), ("a", "nope")]:
        r = host.book(BookingRequest(request_id="r", clinic_id=cid, slot_id=sid,
                                     patient_address="p", expected_version=0))
        assert not r.ok and r.reason == "slot_taken"


def test_race_one_winner(host):
    o = host.offers_for(make_request(clinic_ids=["a"]), now=NOW)[0]
    req = BookingRequest(request_id="r", clinic_id="a", slot_id=o.slot_id, patient_address="p",
                         expected_version=o.slot_version)
    assert [host.book(req).ok, host.book(req).ok] == [True, False]


def test_same_slot_id_in_two_clinics_does_not_collide():
    h = ClinicHost(MemoryStore())
    for cid in ("x", "y"):
        h.add_clinic(profile(cid, slots=[{"slot_id": "s1", "time": "2026-10-26T09:00:00", "price": 10}]))
    h.book(BookingRequest(request_id="r", clinic_id="x", slot_id="s1", patient_address="p", expected_version=0))
    assert h.slots("y").get("s1")["state"] == "open"


def test_add_clinic_is_idempotent(host):
    host.add_clinic(profile("a", "Alpha"))
    assert sorted(host.clinic_ids()) == ["a", "b"]
    assert len(host.slots("a").all()) == 1


def test_cancel_booking_frees_slot_and_emits_event(host):
    o = host.offers_for(make_request(clinic_ids=["a"]), now=NOW)[0]
    host.book(BookingRequest(request_id="r", clinic_id="a", slot_id=o.slot_id, patient_address="p",
                             expected_version=o.slot_version))
    ev = host.cancel_booking("a", o.slot_id, now=NOW)
    assert ev.clinic_id == "a" and ev.slot_id == o.slot_id
    assert host.cancel_booking("a", o.slot_id, now=NOW) is None  # nothing left to cancel
    assert len(host.offers_for(make_request(clinic_ids=["a"]), now=NOW)) == 1


def test_add_and_remove_slot(host):
    sid = host.add_slot("a", "2026-10-27T10:00:00", 120)
    assert host.slots("a").get(sid)["deposit"] == 12.0
    assert host.remove_slot("a", sid) is True


def test_chat_commands_and_owner_check():
    h = ClinicHost(MemoryStore())
    h.add_clinic(profile("a", "Alpha", owner="owner1"))
    assert "not authorized" in h.handle_command("a", "stranger", "add slot 2026-10-27T10:00 120", now=NOW)[0]
    reply, ev = h.handle_command("a", "owner1", "add slot 2026-10-27T10:00 120", now=NOW)
    assert "Added" in reply and ev is None
    assert "a-1" in h.handle_command("a", "owner1", "list slots", now=NOW)[0]
    h.book(BookingRequest(request_id="r", clinic_id="a", slot_id="a-1", patient_address="p", expected_version=0))
    reply, ev = h.handle_command("a", "owner1", "cancel booking a-1", now=NOW)
    assert ev is not None and "freed" in reply.lower()
    assert "Unknown command" in h.handle_command("a", "owner1", "dance", now=NOW)[0]
