"""Frozen message contracts shared by every agent. Change a field only with a group OK."""
from datetime import datetime
from typing import Optional

try:
    from uagents import Model
except ImportError:  # core/tests can run without the agent framework
    from pydantic import BaseModel as Model


class LatLng(Model):
    lat: float
    lng: float


class TimeWindow(Model):
    start: datetime
    end: datetime


class SlotRequest(Model):
    request_id: str
    specialty: str
    time_window: TimeWindow
    location: LatLng
    radius_miles: float
    insurance: str
    max_deposit: float
    patient_address: str


class SlotOffer(Model):
    request_id: str
    clinic_id: str
    clinic_name: str
    slot_id: str
    slot_time: datetime
    price: float
    deposit: float
    distance_miles: float
    expires_at: datetime
    clinic_address: str
    slot_version: int = 0  # echoed back as BookingRequest.expected_version
    # empty means "accepts any"; the clinic already filtered on insurance
    insurance_accepted: list[str] = []


class RankedOffers(Model):
    request_id: str
    offers: list[SlotOffer]


class BookingRequest(Model):
    request_id: str
    clinic_id: str
    slot_id: str
    patient_address: str
    expected_version: int


class BookingResult(Model):
    ok: bool
    slot_id: str
    reason: str  # confirmed | slot_taken | expired
    confirmation_id: Optional[str] = None


class PaymentIntent(Model):
    booking_id: str
    amount: float
    status: str = "pending"  # pending | release | refund (instruction to escrow)


class PaymentReceipt(Model):
    booking_id: str
    amount: float
    status: str  # held | released | refunded
    tx_ref: str


class CancellationEvent(Model):
    clinic_id: str
    slot_id: str
    slot_time: datetime
    freed_at: datetime
