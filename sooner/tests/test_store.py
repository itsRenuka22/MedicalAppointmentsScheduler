from sooner.agents.escrow_agent import EscrowLogic
from sooner.core.escrow import Escrow
from sooner.core.slotbook import SlotBook
from sooner.core.store import CtxStore, MemoryStore
from sooner.shared.models import PaymentIntent


class FakeCtxStorage:  # mimics uagents ctx.storage
    def __init__(self): self.d = {}
    def get(self, k): return self.d.get(k)
    def set(self, k, v): self.d[k] = v
    def remove(self, k): del self.d[k]


def test_memory_store_roundtrip_and_default():
    s = MemoryStore()
    assert s.get("x", 5) == 5
    s.set("x", {"a": [1, 2]})
    assert s.get("x") == {"a": [1, 2]}
    s.delete("x"); s.delete("x")
    assert s.get("x") is None


def test_ctx_store_adapter():
    s = CtxStore(FakeCtxStorage())
    assert s.get("k", 1) == 1
    s.set("k", 2); assert s.get("k") == 2
    s.delete("k"); s.delete("k")  # deleting a missing key is fine
    assert s.get("k") is None


def test_state_survives_new_instances_over_one_store():
    s = MemoryStore()
    eid = Escrow(s).hold(10)
    assert Escrow(s).release(eid) == "released"
    logic = EscrowLogic(s)
    logic.handle_intent(PaymentIntent(booking_id="b", amount=5))
    assert EscrowLogic(s).handle_intent(
        PaymentIntent(booking_id="b", amount=5, status="refund")).status == "refunded"


def test_slotbook_cas_over_ctx_store():
    book = SlotBook(CtxStore(FakeCtxStorage()), "c1")
    book.add("s1", "2026-10-26T09:00:00", 100, 10)
    assert book.try_hold("s1", 0) == (True, 1, "held")
    assert book.try_hold("s1", 0)[0] is False
