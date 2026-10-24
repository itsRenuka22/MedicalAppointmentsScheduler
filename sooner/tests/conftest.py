from datetime import datetime, timedelta

from sooner.shared.models import LatLng, SlotOffer, SlotRequest, TimeWindow

T0 = datetime(2026, 10, 26, 8, 0)


def make_request(**kw) -> SlotRequest:
    d = dict(request_id="r1", specialty="dermatology",
             time_window=TimeWindow(start=T0, end=T0 + timedelta(days=3)),
             location=LatLng(lat=37.7946, lng=-122.3950), radius_miles=10,
             insurance="Aetna", max_deposit=50, patient_address="x")
    d.update(kw)
    return SlotRequest(**d)


def make_offer(clinic="c1", slot="s1", hours=1, dist=1.0, deposit=10.0, **kw) -> SlotOffer:
    d = dict(request_id="r1", clinic_id=clinic, clinic_name=clinic, slot_id=slot,
             slot_time=T0 + timedelta(hours=hours), price=100, deposit=deposit,
             distance_miles=dist, expires_at=T0, clinic_address="a")
    d.update(kw)
    return SlotOffer(**d)
