"""Clinic onboarding conversation: parse (ASI:One LLM, regex fallback), merge drafts, ask for gaps."""
import json
import os
import re
import urllib.request
from datetime import datetime
from typing import Callable, Optional

from sooner.core.registry import REQUIRED, OnboardResult, Registry

PROMPT = ("Extract a clinic description as JSON with keys: name, address, specialties (list), "
          "insurance (list of accepted insurers), slots (list of {time: ISO 8601 local datetime, "
          "price: number}). Omit keys that are not stated. Reply with JSON only.")
SLOT_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})\s*(?:\$|usd\s*)?(\d+(?:\.\d+)?)", re.I)
FIELDS = {"name": "name", "address": "address", "specialties": "specialties", "specialty": "specialties",
          "insurance": "insurance", "insurances": "insurance"}


def asi1_clinic_llm(text: str) -> dict:
    req = urllib.request.Request(
        "https://api.asi1.ai/v1/chat/completions",
        data=json.dumps({"model": "asi1-mini", "messages": [
            {"role": "system", "content": PROMPT}, {"role": "user", "content": text}]}).encode(),
        headers={"Authorization": f"Bearer {os.getenv('ASI1_API_KEY', '')}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        content = json.load(r)["choices"][0]["message"]["content"]
    return json.loads(re.search(r"\{.*\}", content, re.S).group(0))


def _regex_parse(text: str) -> dict:
    out: dict = {}
    for line in re.split(r"[\n;]", text):
        m = re.match(r"\s*(name|address|specialt(?:y|ies)|insurances?)\s*[:=]\s*(.+?)\s*$", line, re.I)
        if m:
            key, val = FIELDS[m.group(1).lower()], m.group(2)
            out[key] = [x.strip() for x in val.split(",") if x.strip()] if key in ("specialties", "insurance") else val
    slots = [{"time": f"{d}T{t.zfill(5)}", "price": float(p)} for d, t, p in SLOT_RE.findall(text)]
    if slots:
        out["slots"] = slots
    return out


def parse_clinic_text(text: str, llm: Optional[Callable[[str], dict]] = None) -> dict:
    """LLM first (when a key is set or llm is given); regex always fills what it missed."""
    if llm is None and os.getenv("ASI1_API_KEY"):
        llm = asi1_clinic_llm
    parsed = _regex_parse(text)
    if llm is not None:
        try:
            got = llm(text)
            parsed = {**parsed, **{k: v for k, v in got.items() if v not in (None, "", [])}}
        except Exception:
            pass
    return parsed


def merge_draft(draft: dict, new: dict) -> dict:
    merged = {**draft, **{k: v for k, v in new.items() if k != "slots"}}
    slots = list(draft.get("slots", [])) + [s for s in new.get("slots", []) if s not in draft.get("slots", [])]
    if slots:
        merged["slots"] = slots
    return merged


HELP = ("Describe your clinic, one field per line:\n"
        "name: Smile Dental\naddress: 12 Pine St, San Francisco, CA\nspecialties: dental\n"
        "insurance: Aetna, Cigna\nslots: 2026-10-27 10:00 $120, 2026-10-28 14:30 $150")


class RegistryChat:
    def __init__(self, registry: Registry):
        self.registry = registry

    def handle(self, sender: str, text: str, llm=None, now: Optional[datetime] = None):
        """Returns (reply, OnboardResult | None). A draft is kept per sender until complete."""
        store = self.registry.store
        m = re.match(r"\s*deregister\s+(\S+)\s*$", text, re.I)
        if m:
            return self.registry.deregister(m.group(1), sender)[1], None
        draft = merge_draft(store.get(f"draft:{sender}", {}), parse_clinic_text(text, llm))
        if not draft:
            return HELP, None
        result: OnboardResult = self.registry.onboard(draft, now=now, owner=sender)
        if result.missing:
            store.set(f"draft:{sender}", draft)
            return "Thanks. I still need: " + ", ".join(result.missing) + ".\n\n" + HELP, None
        store.delete(f"draft:{sender}")
        return result.message, result
