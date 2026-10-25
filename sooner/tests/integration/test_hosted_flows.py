import pytest

from sooner.tests.integration.hosted_world import LLM, World

DENTAL = """name: Smile Dental
address: 12 Pine St, San Francisco, CA
specialties: dentist
insurance: Aetna
slots: 2026-10-27 10:00 $120, 2026-10-28 14:30 $150"""
DENTAL_LLM = lambda t: {"specialty": "dentist", "days_ahead": 6, "insurance": "Aetna",
                        "max_deposit": 40, "radius_miles": 10}


@pytest.fixture
def world():
    w = World()
    w.seed()
    w.user_stores = {}
    return w


async def test_seed_clinics_go_through_registry_into_the_hub(world):
    es = {e["clinic_id"]: e for e in world.registry.entries()}
    assert set(es) == {"clinic_downtown", "clinic_bayside", "clinic_northgate"}
    assert all(e["host"] == "hub" and e["agent_address"] == "agent-hub" for e in es.values())


async def test_search_and_book_by_name_uses_one_hub_query(world):
    p = world.patient("u1")
    text = await p.handle_message("derm please")
    assert "Bayside" in text and "Downtown" in text and "Northgate" not in text
    assert world.msgs["matchmaker->clinic"] == 2  # ONE query to the hub for both clinics
    out = await world.patient("u1").handle_message("book Bayside")
    assert "Booked Bayside" in out and "(simulated)" in out


async def test_new_dental_clinic_is_findable_and_bookable(world):
    reply, res = world.register("owner1", DENTAL)
    assert res.ok and res.host == "dedicated" and res.agent_address in world.agents
    p = world.patient("u1")
    p.llm = DENTAL_LLM
    text = await p.handle_message("I need a dentist, Aetna")
    assert "Smile Dental" in text and "Mon Oct 26" not in text
    out = await world.patient("u1").handle_message("book 1")
    assert "Booked Smile Dental" in out


async def test_race_winner_books_loser_refunded(world):
    a, b = world.patient("u1"), world.patient("u2")
    await a.handle_message("derm"); await b.handle_message("derm")
    ra = await a.handle_message("book 1")
    rb = await b.handle_message("book 1")
    assert "Booked" in ra and "just taken" in rb and "refunded" in rb
    states = sorted(s for _, s in world.escrow.escrow._state.values())
    assert states == ["refunded", "released"]


async def test_cancellation_reoffers_to_waiting_patient(world):
    first = world.patient("u1")
    first.llm = LLM
    await first.handle_message("derm"); await first.handle_message("book 1")  # takes Bayside bs-1
    # narrow the search so nothing matches now, joining the waitlist
    waiting = world.patient("u2")
    waiting.llm = lambda t: {"specialty": "dermatology", "days_ahead": 2, "insurance": "Aetna",
                             "max_deposit": 25, "radius_miles": 10}
    world.agents["agent-hub"].remove_slot("clinic_downtown", "clinic_downtown-1")
    for cid in ("clinic_downtown", "clinic_bayside"):
        for sid, s in list(world.agents["agent-hub"].slots(cid).all().items()):
            if s["state"] == "open":
                world.agents["agent-hub"].remove_slot(cid, sid)
    assert "No matching slots" in await waiting.handle_message("derm tomorrow")
    ev = await world.cancel("agent-hub", "clinic_bayside", "clinic_bayside-1")
    assert ev is not None
    addr, push = world.pushed[0]
    assert addr == "u2"
    text = world.patient("u2").accept_reoffer(push)
    assert "just opened" in text.lower() and "Bayside" in text
    assert "Booked Bayside" in await world.patient("u2").handle_message("book 1")


async def test_full_account_falls_back_to_hub_and_registration_still_succeeds():
    w = World(max_dedicated=0); w.seed(); w.user_stores = {}
    reply, res = w.register("owner1", DENTAL)
    assert res.ok and res.host == "hub" and "hub" in reply.lower()
    p = w.patient("u1"); p.llm = DENTAL_LLM
    assert "Smile Dental" in await p.handle_message("dentist")


async def test_provisioning_failure_does_not_break_search():
    w = World(fail_provision=True); w.seed(); w.user_stores = {}
    reply, res = w.register("owner1", DENTAL)
    assert res.ok and res.host == "hub" and "402" in reply
    assert "Bayside" in await w.patient("u1").handle_message("derm")


async def test_clinic_marked_unavailable_is_skipped_but_search_still_works(world):
    world.register("owner1", DENTAL)
    cid = [e for e in world.registry.entries() if e["name"] == "Smile Dental"][0]["clinic_id"]
    world.registry.set_status(cid, "unavailable")
    assert "Bayside" in await world.patient("u1").handle_message("derm")


async def test_message_budget(world):
    p = world.patient("u1")
    await p.handle_message("derm")
    search = sum(world.msgs.values())
    world.msgs.clear()
    await world.patient("u1").handle_message("book 1")
    booking = sum(world.msgs.values())
    print(f"messages: search={search} booking={booking}")
    assert search <= 6 and booking <= 8
