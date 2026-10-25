"""Clinic registry: validation, duplicate detection, and hosting placement
(dedicated hosted agent until the cap or any creation failure, otherwise the hub)."""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol

from sooner.core.store import Store
from sooner.shared.specialty import normalize_specialty

REQUIRED = ["name", "address", "specialties", "insurance", "slots"]
DEFAULT_LAT, DEFAULT_LNG = 37.7749, -122.4194  # approximate: no geocoder available


class ProvisionError(Exception):
    def __init__(self, message: str, address: Optional[str] = None):
        super().__init__(message)
        self.address = address  # set when an agent was half-created and needs cleanup


class Provisioner(Protocol):
    def create_dedicated(self, record: dict, profile: dict) -> str: ...
    def delete(self, address: str) -> None: ...


@dataclass
class OnboardResult:
    ok: bool
    message: str = ""
    clinic_id: str = ""
    host: str = ""
    agent_address: str = ""
    missing: list = field(default_factory=list)
    hub_add: bool = False  # caller must send the profile to the hub
    profile: Optional[dict] = None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "clinic"


def _valid_slot(s: dict, now: Optional[datetime]) -> bool:
    try:
        when = datetime.fromisoformat(str(s["time"]).replace(" ", "T"))
        return float(s["price"]) > 0 and (now is None or when > now)
    except (KeyError, ValueError, TypeError):
        return False


class Registry:
    def __init__(self, store: Store, provisioner: Provisioner, max_dedicated: int = 2,
                 hub_address: str = ""):
        self.store, self.prov = store, provisioner
        self.max_dedicated, self.hub_address = max_dedicated, hub_address

    def _records(self) -> dict:
        return self.store.get("reg:clinics", {})

    def get(self, clinic_id: str) -> Optional[dict]:
        return self._records().get(clinic_id)

    def entries(self, include_unavailable: bool = False) -> list[dict]:
        return [r for r in self._records().values()
                if r["status"] == "active" or (include_unavailable and r["status"] != "removed")]

    def set_status(self, clinic_id: str, status: str) -> None:
        recs = self._records()
        if clinic_id in recs:
            recs[clinic_id]["status"] = status
            self.store.set("reg:clinics", recs)

    def dedicated_count(self) -> int:
        return sum(1 for r in self._records().values() if r["host"] == "dedicated" and r["status"] != "removed")

    def deregister(self, clinic_id: str, requester: str):
        """Owner-only. Hides the clinic from search; a dedicated agent is deleted to free the quota."""
        rec = self.get(clinic_id)
        if rec is None or not rec.get("owner") or rec["owner"] != requester or rec["status"] == "removed":
            return False, f"Not allowed: {clinic_id} is unknown or not yours."
        if rec["host"] == "dedicated" and rec["agent_address"]:
            try:
                self.prov.delete(rec["agent_address"])
            except Exception as e:
                return False, f"Could not delete the clinic agent ({e}); nothing changed."
        recs = self._records()
        recs[clinic_id]["status"] = "removed"
        self.store.set("reg:clinics", recs)
        return True, f"{rec['name']} was removed from Sooner" + (
            "; its dedicated agent was deleted." if rec["host"] == "dedicated" else ".")

    def onboard(self, profile: dict, prefer_hub: bool = False, now: Optional[datetime] = None,
                owner: str = "") -> OnboardResult:
        now = now or datetime.now()  # slots must be in the future
        missing = [k for k in REQUIRED if not profile.get(k)]
        if missing:
            return OnboardResult(False, f"Missing: {', '.join(missing)}", missing=missing)
        slots = [s for s in profile["slots"] if _valid_slot(s, now)]
        if not slots:
            return OnboardResult(False, "No valid slots: each needs a future date/time and a price above 0.")
        key = (_norm(profile["name"]), _norm(profile["address"]))
        recs = self._records()
        if any((_norm(r["name"]), _norm(r["address"])) == key and r["status"] != "removed" for r in recs.values()):
            return OnboardResult(False, f"{profile['name']} at {profile['address']} is already registered.")
        cid, n = _slug(profile.get("clinic_id") or profile["name"]), 2
        base = cid
        while cid in recs:
            cid, n = f"{base}_{n}", n + 1
        full = {
            "clinic_id": cid, "name": profile["name"].strip(), "address": profile["address"].strip(),
            "lat": float(profile.get("lat") or DEFAULT_LAT), "lng": float(profile.get("lng") or DEFAULT_LNG),
            "specialties": [normalize_specialty(x) for x in profile["specialties"]],
            "insurance": [str(x).strip() for x in profile["insurance"]],
            "deposit_pct": float(profile.get("deposit_pct") or 0.15), "owner": owner or profile.get("owner", ""),
            "slots": [{"slot_id": f"{cid}-{i}", "time": datetime.fromisoformat(str(s["time"]).replace(" ", "T")).isoformat(),
                       "price": float(s["price"])} for i, s in enumerate(slots, 1)],
        }
        record = {"clinic_id": cid, "name": full["name"], "address": full["address"],
                  "specialties": full["specialties"], "insurances": full["insurance"],
                  "host": "", "agent_address": "", "status": "active", "owner": full["owner"]}
        note = ""
        if not prefer_hub and self.dedicated_count() < self.max_dedicated:
            try:
                record["agent_address"] = self.prov.create_dedicated(record, full)
                record["host"] = "dedicated"
            except Exception as e:  # quota, 4xx, 5xx, half-created: never fail the registration
                addr = getattr(e, "address", None)
                if addr:
                    try:
                        self.prov.delete(addr)
                    except Exception:
                        pass
                note = f"Could not create a dedicated agent ({e}); "
        elif not prefer_hub:
            note = f"Dedicated agent limit ({self.max_dedicated}) reached; "
        hub_add = False
        if not record["host"]:
            record["host"], record["agent_address"], hub_add = "hub", self.hub_address, True
            if not self.hub_address:
                record["status"] = "unavailable"
            note += ("your clinic is hosted-in-hub on the shared clinic hub instead." if not prefer_hub
                     else "Hosted in the shared clinic hub.")
        recs[cid] = record
        self.store.set("reg:clinics", recs)
        msg = f"Registered {record['name']} ({cid}). " + (note or "Dedicated agent created.")
        msg += f" Serving agent: {record['agent_address'] or 'none yet'}."
        return OnboardResult(True, msg.strip(), cid, record["host"], record["agent_address"],
                             hub_add=hub_add, profile=full)
