from sooner.agents.escrow_agent import EscrowLogic
from sooner.agents.intent import parse_intent, regex_parse
from sooner.cards.interactive_cards import parse_tap
from sooner.shared.models import LatLng, PaymentIntent

LOC = LatLng(lat=0, lng=0)


def test_three_phrasings_parse():
    for text, spec, ins in [("I need a dermatologist tomorrow, Aetna", "dermatology", "Aetna"),
                            ("general checkup this week with Cigna, deposit under $30", "general", "Cigna"),
                            ("cardiology appointment within 5 miles, Kaiser", "cardiology", "Kaiser")]:
        r = parse_intent(text, LOC, "addr", llm=regex_parse)
        assert r.specialty == spec and r.insurance == ins


def test_llm_failure_falls_back():
    def boom(t): raise RuntimeError
    assert parse_intent("dermatologist", LOC, "a", llm=boom).specialty == "dermatology"


def test_tap_parsing():
    assert parse_tap("book:c1:s1") == ("c1", "s1")
    assert parse_tap("hello") is None


def test_escrow_agent_flow():
    e = EscrowLogic()
    assert e.handle_intent(PaymentIntent(booking_id="b", amount=5)).status == "held"
    assert e.handle_intent(PaymentIntent(booking_id="b", amount=5, status="refund")).status == "refunded"


def test_llm_specialty_is_normalized():
    llm = lambda t: {"specialty": "Dermatologist", "days_ahead": 3, "insurance": "Aetna",
                     "max_deposit": 40, "radius_miles": 10}
    assert parse_intent("x", LOC, "a", llm=llm).specialty == "dermatology"


def test_llm_null_fields_fall_back_to_defaults():
    llm = lambda t: {"specialty": "dermatology", "days_ahead": None, "insurance": "Aetna",
                     "max_deposit": None, "radius_miles": None}
    r = parse_intent("x", LOC, "a", llm=llm)
    assert r.max_deposit == 50.0 and r.radius_miles == 10.0
