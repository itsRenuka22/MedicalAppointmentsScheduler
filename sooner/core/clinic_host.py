"""Hosts one or more clinics over a Store. A dedicated clinic agent hosts one clinic;
the hub hosts several and routes every message by clinic_id."""
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sooner.core.policy import Clinic
from sooner.core.slotbook import BOOKED, HELD, OPEN, SlotBook
from sooner.core.slots import Slot
from sooner.core.store import Store
from sooner.shared.models import (BookingRequest, BookingResult, CancellationEvent,
                                  SlotOffer, SlotRequest)

OFFER_TTL_S = 120


class ClinicHost:
    def __init__(self, store: Store):
        self.store = store

    # --- clinics -----------------------------------------------------------------
    def _profiles(self) -> dict:
        return self.store.get("clinics", {})

    def clinic_ids(self) -> list[str]:
        return list(self._profiles())

    def profile(self, clinic_id: str) -> Optional[dict]:
        return self._profiles().get(clinic_id)

    def slots(self, clinic_id: str) -> SlotBook:
        return SlotBook(self.store, clinic_id)

    def add_clinic(self, profile: dict) -> bool:
        """Idempotent: an already-hosted clinic is left untouched."""
        cid = profile["clinic_id"]
        profiles = self._profiles()
        if cid in profiles:
            return False
        meta = {k: v for k, v in profile.items() if k != "slots"}
        meta.setdefault("owner", "")
        profiles[cid] = meta
        self.store.set("clinics", profiles)
        for s in profile.get("slots", []):
            self.add_slot(cid, s["time"], s["price"], slot_id=s.get("slot_id"))
        return True

    # --- slots -------------------------------------------------------------------
    def add_slot(self, clinic_id: str, time_iso: str, price: float, slot_id: Optional[str] = None) -> str:
        book, p = self.slots(clinic_id), self.profile(clinic_id)
        n = self.store.get(f"next_slot:{clinic_id}", 1)
        while slot_id is None:
            cand = f"{clinic_id}-{n}"
            n += 1
            slot_id = cand if book.get(cand) is None else None
        self.store.set(f"next_slot:{clinic_id}", n)
        book.add(slot_id, time_iso, price, round(price * p["deposit_pct"], 2))
        return slot_id

    def remove_slot(self, clinic_id: str, slot_id: str) -> bool:
        return self.slots(clinic_id).remove(slot_id)

    def cancel_booking(self, clinic_id: str, slot_id: str, now: Optional[datetime] = None):
        book, s = self.slots(clinic_id), self.slots(clinic_id).get(slot_id)
        if s is None or s["state"] not in (HELD, BOOKED) or not book.free(slot_id):
            return None
        return CancellationEvent(clinic_id=clinic_id, slot_id=slot_id,
                                 slot_time=datetime.fromisoformat(s["time"]),
                                 freed_at=now or datetime.now())

    # --- protocol handlers ---------------------------------------------------------
    def _to_clinic(self, clinic_id: str) -> Clinic:
        p = self.profile(clinic_id)
        slots = []
        for sid, s in self.slots(clinic_id).all().items():
            slots.append(Slot(sid, datetime.fromisoformat(s["time"]), s["price"], s["deposit"],
                              state=s["state"], version=s["version"]))
        return Clinic(clinic_id, p["name"], p["address"], p["lat"], p["lng"], p["specialties"],
                      p["insurance"], p["deposit_pct"], slots)

    def offers_for(self, req: SlotRequest, now: Optional[datetime] = None) -> list[SlotOffer]:
        now = now or datetime.now()
        offers = []
        for cid in (req.clinic_ids or self.clinic_ids()):
            if self.profile(cid) is None:
                continue
            clinic = self._to_clinic(cid)
            if not clinic.matches(req):
                continue
            slot = clinic.soonest_slot(req)
            price, deposit = clinic.price_and_deposit(slot)
            offers.append(SlotOffer(
                request_id=req.request_id, clinic_id=cid, clinic_name=clinic.name,
                slot_id=slot.slot_id, slot_time=slot.time, price=price, deposit=deposit,
                distance_miles=round(clinic.distance_to(req), 2),
                expires_at=now + timedelta(seconds=OFFER_TTL_S), clinic_address=clinic.address,
                slot_version=slot.version, insurance_accepted=clinic.insurance))
        return offers

    def book(self, req: BookingRequest, now: Optional[datetime] = None) -> BookingResult:
        taken = BookingResult(ok=False, slot_id=req.slot_id, reason="slot_taken")
        if self.profile(req.clinic_id) is None:
            return taken
        book = self.slots(req.clinic_id)
        s = book.get(req.slot_id)
        if s is None:
            return taken
        if now is not None and datetime.fromisoformat(s["time"]) < now:
            return BookingResult(ok=False, slot_id=req.slot_id, reason="expired")
        ok, _, reason = book.try_hold(req.slot_id, req.expected_version)
        if not ok:
            return BookingResult(ok=False, slot_id=req.slot_id, reason=reason)
        book.confirm(req.slot_id)
        return BookingResult(ok=True, slot_id=req.slot_id, reason="confirmed",
                             confirmation_id=f"conf-{uuid.uuid4().hex[:8]}")

    # --- chat management by the clinic ---------------------------------------------
    def handle_command(self, clinic_id: str, sender: str, text: str,
                       now: Optional[datetime] = None):
        """Returns (reply, CancellationEvent | None)."""
        p = self.profile(clinic_id)
        if p is None:
            return f"Unknown clinic {clinic_id}.", None
        if p.get("owner") and sender != p["owner"]:
            return "You are not authorized to manage this clinic.", None
        t = text.strip()
        m = re.match(r"add slot\s+(\S+(?:\s+\d{1,2}:\d{2})?)\s+\$?(\d+(?:\.\d+)?)$", t, re.I)
        if m:
            try:
                when = datetime.fromisoformat(m.group(1).replace(" ", "T"))
            except ValueError:
                return "Could not read that time. Use: add slot 2026-10-28T10:00 150", None
            sid = self.add_slot(clinic_id, when.isoformat(), float(m.group(2)))
            return f"Added slot {sid} at {when:%a %b %d %I:%M %p} for ${float(m.group(2)):.2f}.", None
        if re.match(r"list slots$", t, re.I):
            rows = [f"{sid}: {s['time']} ${s['price']:.2f} ({s['state']})"
                    for sid, s in sorted(self.slots(clinic_id).all().items(), key=lambda kv: kv[1]["time"])]
            return "\n".join(rows) or "No slots.", None
        m = re.match(r"cancel booking\s+(\S+)$", t, re.I)
        if m:
            ev = self.cancel_booking(clinic_id, m.group(1), now)
            return (f"Booking on {m.group(1)} cancelled; the slot is freed and re-offered to waiting patients."
                    if ev else f"No booking to cancel on {m.group(1)}."), ev
        m = re.match(r"remove slot\s+(\S+)$", t, re.I)
        if m:
            return ("Removed." if self.remove_slot(clinic_id, m.group(1))
                    else "Only open slots can be removed."), None
        return ("Unknown command. Try: add slot 2026-10-28T10:00 150 | list slots | "
                "cancel booking <slot_id> | remove slot <slot_id>"), None
