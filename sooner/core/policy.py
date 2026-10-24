"""Per-clinic match, price, and deposit rules."""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sooner.core.slots import OPEN, Slot
from sooner.shared.models import SlotRequest

DATA = Path(__file__).resolve().parent.parent / "data" / "clinics.json"


def haversine_miles(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(a))


@dataclass
class Clinic:
    clinic_id: str
    name: str
    address: str
    lat: float
    lng: float
    specialties: list[str]
    insurance: list[str]
    deposit_pct: float
    slots: list[Slot] = field(default_factory=list)

    def distance_to(self, request: SlotRequest) -> float:
        return haversine_miles(self.lat, self.lng, request.location.lat, request.location.lng)

    def price_and_deposit(self, slot: Slot) -> tuple[float, float]:
        return slot.price, round(slot.price * self.deposit_pct, 2)

    def _eligible(self, s: Slot, request: SlotRequest) -> bool:
        w = request.time_window
        return (s.state == OPEN and w.start <= s.time <= w.end
                and self.price_and_deposit(s)[1] <= request.max_deposit)

    def matches(self, request: SlotRequest) -> bool:
        if request.specialty.lower() not in (x.lower() for x in self.specialties):
            return False
        if request.insurance not in self.insurance:
            return False
        if self.distance_to(request) > request.radius_miles:
            return False
        return self.soonest_slot(request, _check=False) is not None

    def soonest_slot(self, request: SlotRequest, _check: bool = True) -> Optional[Slot]:
        if _check and not self.matches(request):
            return None
        eligible = [s for s in self.slots if self._eligible(s, request)]
        return min(eligible, key=lambda s: s.time, default=None)


def load_clinics(path: Path = DATA) -> dict[str, Clinic]:
    raw = json.loads(Path(path).read_text())
    clinics = {}
    for c in raw["clinics"]:
        slots = []
        for s in c["slots"]:
            slot = Slot(s["slot_id"], datetime.fromisoformat(s["time"]), s["price"], 0.0)
            slots.append(slot)
        clinic = Clinic(c["clinic_id"], c["name"], c["address"], c["lat"], c["lng"],
                        c["specialties"], c["insurance"], c["deposit_pct"], slots)
        for slot in slots:
            slot.deposit = clinic.price_and_deposit(slot)[1]
        clinics[clinic.clinic_id] = clinic
    return clinics
