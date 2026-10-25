from datetime import datetime

import pytest

from sooner.core.registry import ProvisionError, Registry
from sooner.core.store import MemoryStore

NOW = datetime(2026, 10, 25, 8, 0)


class FakeProvisioner:
    def __init__(self, fail_after=None, fail_always=False):
        self.created, self.deleted, self.fail_always = [], [], fail_always

    def create_dedicated(self, record, profile):
        if self.fail_always:
            raise ProvisionError("HTTP 402 quota exceeded")
        addr = f"agent-dedicated-{len(self.created) + 1}"
        self.created.append(addr)
        return addr

    def delete(self, address):
        self.deleted.append(address)


def prof(name, address="1 Main St", slots=None, **kw):
    p = dict(name=name, address=address, specialties=["dental"], insurance=["Aetna"],
             slots=slots if slots is not None else [{"time": "2026-10-27T10:00:00", "price": 100}])
    p.update(kw)
    return p


def reg(prov=None, max_dedicated=2):
    return Registry(MemoryStore(), prov or FakeProvisioner(), max_dedicated=max_dedicated,
                    hub_address="agent-hub")


def test_new_clinic_gets_a_dedicated_agent():
    r = reg()
    res = r.onboard(prof("Smile Dental"), now=NOW)
    assert res.ok and res.host == "dedicated" and res.agent_address == "agent-dedicated-1"
    rec = r.get(res.clinic_id)
    assert rec["status"] == "active" and rec["specialties"] == ["dental"]


def test_cap_falls_back_to_hub_and_marks_it():
    r = reg(max_dedicated=2)
    hosts = [r.onboard(prof(f"Clinic {i}", address=f"{i} St"), now=NOW) for i in range(4)]
    assert [h.host for h in hosts] == ["dedicated", "dedicated", "hub", "hub"]
    assert hosts[2].agent_address == "agent-hub" and hosts[2].hub_add
    assert "hub" in hosts[2].message.lower()
    assert all(h.ok for h in hosts)


def test_creation_failure_falls_back_to_hub_without_failing_registration():
    prov = FakeProvisioner(fail_always=True)
    res = reg(prov).onboard(prof("Smile Dental"), now=NOW)
    assert res.ok and res.host == "hub" and res.agent_address == "agent-hub"
    assert "402" in res.message and res.hub_add


def test_failed_creation_does_not_count_against_cap():
    prov = FakeProvisioner(fail_always=True)
    r = reg(prov, max_dedicated=1)
    r.onboard(prof("A", address="1"), now=NOW)
    prov.fail_always = False
    assert r.onboard(prof("B", address="2"), now=NOW).host == "dedicated"


def test_prefer_hub_skips_dedicated():
    prov = FakeProvisioner()
    res = reg(prov).onboard(prof("Seed Clinic"), prefer_hub=True, now=NOW)
    assert res.host == "hub" and prov.created == []


def test_duplicate_clinic_rejected_case_insensitive():
    r = reg()
    assert r.onboard(prof("Smile Dental", "1 Main St"), now=NOW).ok
    dup = r.onboard(prof("  smile DENTAL ", "1 main st"), now=NOW)
    assert not dup.ok and "already" in dup.message.lower()
    assert len(r.entries()) == 1


def test_same_name_different_address_is_a_different_clinic():
    r = reg()
    assert r.onboard(prof("Smile", "1 Main"), now=NOW).ok and r.onboard(prof("Smile", "2 Oak"), now=NOW).ok
    ids = [e["clinic_id"] for e in r.entries()]
    assert len(set(ids)) == 2


def test_clinic_without_valid_slots_ignored():
    r = reg()
    res = r.onboard(prof("No Slots", slots=[{"time": "garbage", "price": 5},
                                           {"time": "2020-01-01T10:00:00", "price": 5},
                                           {"time": "2026-10-27T10:00:00", "price": 0}]), now=NOW)
    assert not res.ok and "slot" in res.message.lower() and r.entries() == []


def test_missing_fields_reported():
    res = reg().onboard({"name": "X"}, now=NOW)
    assert not res.ok and set(res.missing) == {"address", "specialties", "insurance", "slots"}


def test_unavailable_clinics_not_listed():
    r = reg()
    cid = r.onboard(prof("Smile Dental"), now=NOW).clinic_id
    r.set_status(cid, "unavailable")
    assert r.entries() == [] and r.get(cid)["status"] == "unavailable"
    assert len(r.entries(include_unavailable=True)) == 1


def test_half_created_agent_is_cleaned_up_then_hub():
    class Half(FakeProvisioner):
        def create_dedicated(self, record, profile):
            raise ProvisionError("start failed", address="agent-half")
    prov = Half()
    res = reg(prov).onboard(prof("Smile Dental"), now=NOW)
    assert res.host == "hub" and prov.deleted == ["agent-half"]


def test_dedicated_count_survives_new_registry_instance():
    store = MemoryStore()
    Registry(store, FakeProvisioner(), 1, "hub").onboard(prof("A", "1"), now=NOW)
    res = Registry(store, FakeProvisioner(), 1, "hub").onboard(prof("B", "2"), now=NOW)
    assert res.host == "hub"


def test_seed_clinic_message_does_not_claim_a_dedicated_agent():
    res = reg().onboard(prof("Seed Clinic"), prefer_hub=True, now=NOW)
    assert "Dedicated agent created" not in res.message and "hub" in res.message.lower()


def test_owner_can_deregister_and_dedicated_agent_is_deleted():
    prov = FakeProvisioner()
    r = reg(prov)
    res = r.onboard(prof("Smile Dental"), now=NOW, owner="owner1")
    ok, msg = r.deregister(res.clinic_id, "owner1")
    assert ok and prov.deleted == ["agent-dedicated-1"]
    assert r.entries() == [] and r.get(res.clinic_id)["status"] == "removed"
    assert r.dedicated_count() == 0  # the slot is free for the next clinic


def test_only_the_owner_can_deregister():
    prov = FakeProvisioner()
    r = reg(prov)
    cid = r.onboard(prof("Smile Dental"), now=NOW, owner="owner1").clinic_id
    assert r.deregister(cid, "stranger")[0] is False and prov.deleted == []
    seed = r.onboard(prof("Seed", "9 St"), prefer_hub=True, now=NOW).clinic_id  # no owner recorded
    assert r.deregister(seed, "anyone")[0] is False
    assert r.deregister("nope", "owner1")[0] is False


def test_hub_clinic_deregister_only_marks_unavailable():
    prov = FakeProvisioner(fail_always=True)
    r = reg(prov)
    cid = r.onboard(prof("Smile Dental"), now=NOW, owner="owner1").clinic_id
    assert r.deregister(cid, "owner1")[0] and prov.deleted == [] and r.entries() == []
    # a deregistered clinic's name can be registered again
    assert r.onboard(prof("Smile Dental"), now=NOW, owner="owner1").ok
