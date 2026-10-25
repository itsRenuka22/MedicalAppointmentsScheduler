import asyncio
from datetime import datetime

from sooner.agents.matchmaker_agent import Matchmaker
from sooner.core.store import MemoryStore
from sooner.shared.models import CancellationEvent, ClinicEntry, SlotOffers
from sooner.tests.conftest import T0, make_offer, make_request


def entry(cid, agent, specialties=("dermatology",), insurances=("Aetna",), status="active"):
    return ClinicEntry(clinic_id=cid, name=cid, address="a", specialties=list(specialties),
                       insurances=list(insurances), host="hub", agent_address=agent, status=status)


class Net:
    """Fake network: records every (agent, clinic_ids) query."""
    def __init__(self, offers_by_clinic, dead=()):
        self.offers, self.dead, self.calls = offers_by_clinic, set(dead), []

    async def query(self, agent, req):
        self.calls.append((agent, tuple(req.clinic_ids)))
        if agent in self.dead:
            await asyncio.sleep(5)
        return SlotOffers(request_id=req.request_id,
                          offers=[self.offers[c] for c in req.clinic_ids if c in self.offers])


def lister(entries):
    async def f():
        return entries
    return f


def mm(timeout=0.3):
    return Matchmaker(MemoryStore(), timeout=timeout, list_timeout=0.3)


async def test_one_message_per_serving_agent_with_clinic_ids():
    net = Net({"a": make_offer("a", "a1"), "b": make_offer("b", "b1", hours=2), "c": make_offer("c", "c1", hours=3)})
    es = [entry("a", "hub"), entry("b", "hub"), entry("c", "agent-c")]
    out = await mm().search(make_request(), lister(es), net.query)
    assert sorted(net.calls) == [("agent-c", ("c",)), ("hub", ("a", "b"))]
    assert [o.clinic_id for o in out.offers] == ["a", "b", "c"]


async def test_skips_clinics_that_cannot_match_and_unavailable_ones():
    net = Net({"a": make_offer("a", "a1")})
    es = [entry("a", "hub"), entry("dentist", "x", specialties=("dental",)),
          entry("cigna", "y", insurances=("Cigna",)), entry("dead", "z", status="unavailable")]
    await mm().search(make_request(), lister(es), net.query)
    assert net.calls == [("hub", ("a",))]


async def test_dead_agent_dropped_at_timeout_others_returned():
    net = Net({"a": make_offer("a", "a1"), "c": make_offer("c", "c1")}, dead={"agent-c"})
    out = await mm(timeout=0.2).search(make_request(), lister([entry("a", "hub"), entry("c", "agent-c")]), net.query)
    assert [o.clinic_id for o in out.offers] == ["a"]


async def test_registry_down_falls_back_to_last_known_list():
    m = mm()
    net = Net({"a": make_offer("a", "a1")})
    await m.search(make_request(), lister([entry("a", "hub")]), net.query)

    async def broken():
        raise RuntimeError("registry down")
    out = await m.search(make_request(), broken, net.query)
    assert [o.clinic_id for o in out.offers] == ["a"]

    async def slow():
        await asyncio.sleep(5)
    out = await m.search(make_request(), slow, net.query)
    assert [o.clinic_id for o in out.offers] == ["a"]


async def test_no_known_list_and_registry_down_returns_empty():
    async def broken():
        return None
    out = await mm().search(make_request(), broken, Net({}).query)
    assert out.offers == []


async def test_new_clinic_appears_in_next_search():
    m, net = mm(), Net({"a": make_offer("a", "a1"), "n": make_offer("n", "n1", hours=5)})
    es = [entry("a", "hub")]
    await m.search(make_request(), lister(es), net.query)
    es.append(entry("n", "agent-n"))
    out = await m.search(make_request(), lister(es), net.query)
    assert {o.clinic_id for o in out.offers} == {"a", "n"}


async def test_empty_search_joins_waitlist_and_cancellation_pushes_reoffer():
    m, net = mm(), Net({})
    req = make_request(patient_address="user1")
    es = [entry("a", "hub")]
    assert (await m.search(req, lister(es), net.query)).offers == []
    net.offers["a"] = make_offer("a", "a1")  # slot freed
    ev = CancellationEvent(clinic_id="a", slot_id="a1", slot_time=T0, freed_at=T0)
    pushes = await m.on_cancellation(ev, lister(es), net.query)
    assert len(pushes) == 1 and pushes[0].patient_address == "user1" and pushes[0].offers[0].slot_id == "a1"
    assert await m.on_cancellation(ev, lister(es), net.query) == []  # served once


async def test_waitlist_is_capped():
    m = mm()
    for i in range(15):
        await m.search(make_request(patient_address=f"u{i}"), lister([entry("a", "hub")]), Net({}).query)
    assert len(m.store.get("waitlist", [])) == 10
