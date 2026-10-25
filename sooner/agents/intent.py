"""Turn free text into a SlotRequest. ASI:One LLM first; a regex fallback keeps the demo alive."""
import json
import re
import urllib.request
import uuid
from datetime import datetime, timedelta
from typing import Callable, Optional

from sooner.shared import config
from sooner.shared.models import LatLng, SlotRequest, TimeWindow

PROMPT = ("Extract a medical appointment request as JSON with keys: specialty (string), "
          "days_ahead (int, window length from now), insurance (string), max_deposit (number), "
          "radius_miles (number). Reply with JSON only.")


def asi1_llm(text: str) -> dict:
    req = urllib.request.Request(
        "https://api.asi1.ai/v1/chat/completions",
        data=json.dumps({"model": "asi1-mini", "messages": [
            {"role": "system", "content": PROMPT}, {"role": "user", "content": text}]}).encode(),
        headers={"Authorization": f"Bearer {config.ASI1_API_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        content = json.load(r)["choices"][0]["message"]["content"]
    return json.loads(re.search(r"\{.*\}", content, re.S).group(0))


def regex_parse(text: str) -> dict:
    t = text.lower()
    spec = next((s for s in ("dermatology", "dermatologist", "cardiology", "general", "dentist")
                 if s in t), "general")
    spec = {"dermatologist": "dermatology"}.get(spec, spec)
    ins = re.search(r"\b(aetna|kaiser|cigna|blue shield)\b", t)
    dep = re.search(r"(?:deposit|under|max)\D{0,10}\$?(\d+)", t)
    days = 1 if "tomorrow" in t else 7 if "week" in t else 3
    rad = re.search(r"(\d+)\s*(?:mi|miles)", t)
    return {"specialty": spec, "days_ahead": days,
            "insurance": ins.group(1).title() if ins else "Aetna",
            "max_deposit": float(dep.group(1)) if dep else 50.0,
            "radius_miles": float(rad.group(1)) if rad else 10.0}


SPECIALTY_ALIASES = {"dermatologist": "dermatology", "skin": "dermatology",
                     "primary care": "general", "primary": "general", "gp": "general",
                     "dentist": "dental", "dentistry": "dental"}


def normalize_specialty(value: str) -> str:
    """The LLM may say 'dermatologist'; clinics advertise 'dermatology'."""
    v = str(value).strip().lower()
    return SPECIALTY_ALIASES.get(v, v)


def parse_intent(text: str, location: LatLng, address: str, now: Optional[datetime] = None,
                 llm: Optional[Callable[[str], dict]] = None) -> SlotRequest:
    now = now or datetime.now()
    if llm is None:
        llm = asi1_llm if config.ASI1_API_KEY else regex_parse
    d = regex_parse(text)  # defaults for anything the LLM omits or returns as null
    try:
        d.update({k: v for k, v in llm(text).items() if v is not None})
    except Exception:
        pass
    return SlotRequest(
        request_id=uuid.uuid4().hex[:8], specialty=normalize_specialty(d["specialty"]),
        time_window=TimeWindow(start=now, end=now + timedelta(days=int(d["days_ahead"]))),
        location=location, radius_miles=float(d["radius_miles"]), insurance=d["insurance"],
        max_deposit=float(d["max_deposit"]), patient_address=address)
