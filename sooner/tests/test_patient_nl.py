import pytest

from sooner.agents.patient_agent import PatientLogic
from sooner.cards.interactive_cards import resolve_choice
from sooner.core.store import MemoryStore
from sooner.shared.models import (BookingResult, PaymentReceipt, RankedOffers)
from sooner.tests.conftest import make_offer, make_request

LLM = lambda t: {"specialty": "dermatology", "days_ahead": 5, "insurance": "Aetna",
                 "max_deposit": 40, "radius_miles": 10}


def offers():
    return [make_offer("clinic_bayside", "bs-1", clinic_name="Bayside Skin Clinic", hours=1),
            make_offer("clinic_downtown", "dt-1", clinic_name="Downtown Family Care", hours=2),
            make_offer("clinic_downtown2", "dt2-1", clinic_name="Downtown Dermatology", hours=3)]


def test_resolve_choice_forms():
    o = offers()
    assert resolve_choice("book 1", o) == ("clinic_bayside", "bs-1")
    assert resolve_choice("Book #2 please", o) == ("clinic_downtown", "dt-1")
    assert resolve_choice("book bayside", o) == ("clinic_bayside", "bs-1")
    assert resolve_choice("book:clinic_downtown:dt-1", o) == ("clinic_downtown", "dt-1")
    assert resolve_choice("book family", o) == ("clinic_downtown", "dt-1")
    assert resolve_choice("book downtown", o) == "ambiguous"
    assert resolve_choice("book 9", o) == "unknown"
    assert resolve_choice("book zzz", o) == "unknown"
    assert resolve_choice("hello", o) is None


def make_patient(store, sender="user1", paid=None):
    paid = paid if paid is not None else []

    async def ask(req):
        return RankedOffers(request_id=req.request_id, offers=offers())

    async def book(cid, b):
        return BookingResult(ok=True, slot_id=b.slot_id, reason="confirmed", confirmation_id="conf-1")

    async def pay(intent):
        paid.append(intent.status)
        return PaymentReceipt(booking_id=intent.booking_id, amount=intent.amount,
                              status="held", tx_ref="sim:esc-1")
    return PatientLogic(ask, book, pay, llm=LLM, store=store, sender=sender)


async def test_offers_persist_between_messages_and_book_by_number():
    store, paid = MemoryStore(), []
    await make_patient(store, paid=paid).handle_message("derm please")
    out = await make_patient(store, paid=paid).handle_message("book 2")  # a fresh instance
    assert "Booked Downtown Family Care" in out and "(simulated)" in out
    assert paid == ["pending", "release"]


async def test_book_by_name_and_ambiguity_and_nothing_charged_on_bad_choice():
    store, paid = MemoryStore(), []
    await make_patient(store, paid=paid).handle_message("derm please")
    amb = await make_patient(store, paid=paid).handle_message("book downtown")
    assert "more than one" in amb.lower() and paid == []
    assert "Booked Bayside" in await make_patient(store, paid=paid).handle_message("book Bayside")


async def test_book_without_a_search_asks_to_search_first():
    out = await make_patient(MemoryStore()).handle_message("book 1")
    assert "search" in out.lower()


async def test_offers_are_per_sender():
    store = MemoryStore()
    await make_patient(store, "u1").handle_message("derm please")
    assert "search" in (await make_patient(store, "u2").handle_message("book 1")).lower()


async def test_reoffer_push_is_saved_and_bookable():
    store = MemoryStore()
    p = make_patient(store, "user1")
    text = p.accept_reoffer(RankedOffers(request_id="r", offers=offers()[:1], patient_address="user1"))
    assert "just opened" in text.lower() and "Bayside" in text
    assert "Booked Bayside" in await make_patient(store, "user1").handle_message("book 1")
