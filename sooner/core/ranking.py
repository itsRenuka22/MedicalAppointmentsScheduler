"""The sooner score: earliest slot, then nearest, then lowest deposit."""
from sooner.shared.models import SlotOffer, SlotRequest


def _valid(o: SlotOffer, r: SlotRequest) -> bool:
    w = r.time_window
    if not (w.start <= o.slot_time <= w.end):
        return False
    if o.deposit > r.max_deposit or o.distance_miles > r.radius_miles:
        return False
    if o.insurance_accepted and r.insurance not in o.insurance_accepted:
        return False
    return True


def rank(offers: list[SlotOffer], request: SlotRequest) -> list[SlotOffer]:
    valid = [o for o in offers if _valid(o, request)]
    # sorted() is stable, and clinic_id/slot_id make ties fully deterministic
    return sorted(valid, key=lambda o: (o.slot_time, o.distance_miles, o.deposit,
                                        o.clinic_id, o.slot_id))
