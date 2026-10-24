import asyncio

import pytest

from sooner.agents.matchmaker_agent import gather_offers
from sooner.tests.conftest import make_request
from sooner.tests.integration.harness import World

LLM = lambda t: {"specialty": "dermatology", "days_ahead": 5, "insurance": "Aetna",
                 "max_deposit": 40, "radius_miles": 10}


async def test_happy_path():
    w = World(); p = w.patient(LLM)
    text = await p.handle_message("derm please")
    assert "Bayside" in text and text.index("Bayside") < text.index("Downtown")
    out = await p.handle_message(w.first_tap(p))
    assert "Booked" in out and "synthetic" in out
    assert list(w.escrow.escrow._state.values())[0][1] == "released"


async def test_search_never_books_or_pays():
    w = World(); p = w.patient(LLM)
    await p.handle_message("derm please")
    assert w.escrow.by_booking == {}


async def test_race_one_winner_loser_refunded():
    w = World(); a, b = w.patient(LLM), w.patient(LLM)
    await a.handle_message("x"); await b.handle_message("x")
    tap = w.first_tap(a)
    ra, rb = await a.handle_message(tap), await b.handle_message(tap)
    assert "Booked" in ra and "just taken" in rb
    states = sorted(s for _, s in w.escrow.escrow._state.values())
    assert states == ["refunded", "released"]


async def test_clinic_offline_still_returns_others():
    w = World(); w.logics["clinic_bayside"].online = False
    p = w.patient(LLM)
    text = await p.handle_message("x")
    assert "Downtown" in text and "Bayside" not in text


async def test_slow_clinic_dropped_at_timeout():
    w = World(timeout=0.2)
    fast = w._query(w.logics["clinic_downtown"])

    async def slow(req):
        await asyncio.sleep(5)
    offers = await gather_offers(make_request(), [fast, slow], timeout=0.2)
    assert [o.clinic_id for o in offers] == ["clinic_downtown"]


async def test_cancellation_reoffers_slot():
    w = World(); p = w.patient(LLM)
    await p.handle_message("x")
    await p.handle_message(w.first_tap(p))  # books bs-1
    bayside = w.logics["clinic_bayside"]
    assert "bs-1" not in await w.patient(LLM).handle_message("x")
    event = bayside.free_one_slot()
    assert event.slot_id == "bs-1"
    assert "bs-1" in await w.patient(LLM).handle_message("x")
