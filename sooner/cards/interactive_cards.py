"""Builders for slot-selection cards. Rendered as chat text plus a structured payload;
a card tap arrives as a message carrying the action string (see parse_tap)."""
import re

from sooner.shared.config import SYNTHETIC_NOTICE
from sooner.shared.models import SlotOffer

BOOK_PREFIX = "book:"


def offer_card(offer: SlotOffer) -> dict:
    return {
        "title": f"{offer.clinic_name} - {offer.slot_time:%a %b %d, %I:%M %p}",
        "body": (f"${offer.price:.2f} total, ${offer.deposit:.2f} deposit held in escrow "
                 f"(simulated). {offer.distance_miles} mi away. {offer.clinic_address}"),
        "action": {"label": "Book this slot", "value": f"{BOOK_PREFIX}{offer.clinic_id}:{offer.slot_id}"},
    }


def offers_cards(offers: list[SlotOffer]) -> list[dict]:
    return [offer_card(o) for o in offers]


def render_text(cards: list[dict]) -> str:
    if not cards:
        return "No matching slots found right now. " + SYNTHETIC_NOTICE
    lines = [f"{i}. {c['title']}\n   {c['body']}\n   Tap/reply: {c['action']['value']}"
             for i, c in enumerate(cards, 1)]
    return "\n".join(lines) + f"\n\n{SYNTHETIC_NOTICE}"


FILLER = {"book", "option", "number", "no", "the", "slot", "with", "at", "appointment", "please",
          "me", "a", "an", "at", "clinic", "#"}


def resolve_choice(text: str, offers: list):
    """Map 'book 1', 'book Bayside' or 'book:<clinic>:<slot>' onto an offer.
    Returns (clinic_id, slot_id), None (not a booking message), 'ambiguous' or 'unknown'."""
    t = text.strip()
    if not re.match(r"book\b", t, re.I):
        return None
    tap = parse_tap(t)
    if tap:
        return tap if any((o.clinic_id, o.slot_id) == tap for o in offers) else "unknown"
    rest = re.sub(r"[#.,!?]", " ", t.lower()).split()
    tokens = [w for w in rest if w not in FILLER]
    if len(tokens) == 1 and tokens[0].isdigit():
        i = int(tokens[0])
        return (offers[i - 1].clinic_id, offers[i - 1].slot_id) if 1 <= i <= len(offers) else "unknown"
    hits = [o for o in offers if tokens and all(w in o.clinic_name.lower() for w in tokens)]
    if len(hits) == 1:
        return hits[0].clinic_id, hits[0].slot_id
    return "ambiguous" if hits else "unknown"


def parse_tap(text: str):
    """Return (clinic_id, slot_id) if text is a card-tap action, else None."""
    text = text.strip()
    if not text.startswith(BOOK_PREFIX):
        return None
    parts = text[len(BOOK_PREFIX):].split(":")
    return (parts[0], parts[1]) if len(parts) == 2 else None
