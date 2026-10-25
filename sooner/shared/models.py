"""Frozen message contracts shared by every agent. Change a field only with a group OK."""
from datetime import datetime
from typing import Optional

from uagents import Model  # no try/except import: Agentverse's code loader rejects it


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
    # which clinics at the receiving agent to quote; empty means all of its clinics
    clinic_ids: list[str] = []


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
    agent_address: str = ""  # serving agent, set by the matchmaker; bookings go there
    # empty means "accepts any"; the clinic already filtered on insurance
    insurance_accepted: list[str] = []


class SlotOffers(Model):
    """One reply per serving agent (a hub answers for several clinics at once)."""
    request_id: str
    offers: list[SlotOffer]


class RankedOffers(Model):
    request_id: str
    offers: list[SlotOffer]
    patient_address: str = ""  # set on pushes (re-offers after a cancellation)


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


class ClinicEntry(Model):
    clinic_id: str
    name: str
    address: str
    specialties: list[str]
    insurances: list[str]
    host: str  # dedicated | hub
    agent_address: str  # the agent that serves this clinic
    status: str  # active | unavailable


class ClinicListRequest(Model):
    request_id: str = ""


class ClinicListResponse(Model):
    clinics: list[ClinicEntry]


class HubAddClinic(Model):
    """Registry -> hub: host this clinic. profile_json is the clinic profile."""
    profile_json: str


class HubAddResult(Model):
    clinic_id: str
    ok: bool
    detail: str = ""


class RegisterClinic(Model):
    """Structured onboarding (used to seed clinics through the same path as chat)."""
    profile_json: str
    prefer_hub: bool = False


class RegisterClinicResult(Model):
    ok: bool
    clinic_id: str = ""
    host: str = ""
    agent_address: str = ""
    message: str = ""
