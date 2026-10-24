"""ClinicAgent: offers its soonest slot, holds on booking, frees slots on cancellation."""
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sooner.core import slots
from sooner.core.policy import Clinic
from sooner.shared import config
from sooner.shared.models import (BookingRequest, BookingResult, CancellationEvent,
                                  SlotOffer, SlotRequest)


class ClinicLogic:
    """Plain-Python handlers; the uAgent wrapper below only forwards messages."""

    def __init__(self, clinic: Clinic):
        self.clinic = clinic
        self.online = True

    def handle_slot_request(self, req: SlotRequest, now: Optional[datetime] = None) -> Optional[SlotOffer]:
        if not self.online or not self.clinic.matches(req):
            return None
        slot = self.clinic.soonest_slot(req)
        price, deposit = self.clinic.price_and_deposit(slot)
        now = now or datetime.now()
        return SlotOffer(
            request_id=req.request_id, clinic_id=self.clinic.clinic_id,
            clinic_name=self.clinic.name, slot_id=slot.slot_id, slot_time=slot.time,
            price=price, deposit=deposit, distance_miles=round(self.clinic.distance_to(req), 2),
            expires_at=now + timedelta(seconds=config.OFFER_TTL_S),
            clinic_address=self.clinic.address, slot_version=slot.version,
            insurance_accepted=self.clinic.insurance)

    def _find(self, slot_id: str):
        return next((s for s in self.clinic.slots if s.slot_id == slot_id), None)

    def handle_booking(self, req: BookingRequest, now: Optional[datetime] = None) -> BookingResult:
        slot = self._find(req.slot_id)
        if slot is None:
            return BookingResult(ok=False, slot_id=req.slot_id, reason="slot_taken")
        if now is not None and slot.time < now:
            return BookingResult(ok=False, slot_id=req.slot_id, reason="expired")
        ok, _, reason = slots.try_hold(slot, req.expected_version)
        if not ok:
            return BookingResult(ok=False, slot_id=req.slot_id, reason=reason)
        slots.confirm(slot)
        return BookingResult(ok=True, slot_id=slot.slot_id, reason="confirmed",
                             confirmation_id=f"conf-{uuid.uuid4().hex[:8]}")

    def free_one_slot(self, now: Optional[datetime] = None) -> Optional[CancellationEvent]:
        """Simulated cancellation: free one booked slot and announce it."""
        booked = [s for s in self.clinic.slots if s.state == slots.BOOKED]
        if not booked:
            return None
        slot = min(booked, key=lambda s: s.time)
        slots.free(slot)
        return CancellationEvent(clinic_id=self.clinic.clinic_id, slot_id=slot.slot_id,
                                 slot_time=slot.time, freed_at=now or datetime.now())


def build_agent(clinic: Clinic, matchmaker_address: str = "", cancel_interval_s: float = 0):
    from uagents import Agent, Context
    cid = clinic.clinic_id
    agent = Agent(name=cid, seed=config.seed(cid), port=config.PORTS[cid],
                  endpoint=[f"http://127.0.0.1:{config.PORTS[cid]}/submit"])
    logic = ClinicLogic(clinic)

    @agent.on_message(SlotRequest, replies={SlotOffer})
    async def on_request(ctx: Context, sender: str, msg: SlotRequest):
        offer = logic.handle_slot_request(msg)
        if offer:
            await ctx.send(sender, offer)

    @agent.on_message(BookingRequest, replies={BookingResult})
    async def on_booking(ctx: Context, sender: str, msg: BookingRequest):
        await ctx.send(sender, logic.handle_booking(msg))

    if cancel_interval_s and matchmaker_address:
        @agent.on_interval(period=cancel_interval_s)
        async def on_tick(ctx: Context):
            event = logic.free_one_slot()
            if event:
                await ctx.send(matchmaker_address, event)

    agent.logic = logic
    return agent
