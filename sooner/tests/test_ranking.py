from datetime import timedelta

from sooner.core.ranking import rank
from sooner.tests.conftest import T0, make_offer, make_request


def ids(offers):
    return [o.slot_id for o in offers]


def test_earliest_first_then_distance_then_deposit():
    offers = [make_offer(slot="c", hours=2), make_offer(slot="b", hours=1, dist=3),
              make_offer(slot="a", hours=1, dist=1, deposit=9), make_offer(slot="a2", hours=1, dist=1, deposit=5)]
    assert ids(rank(offers, make_request())) == ["a2", "a", "b", "c"]


def test_deterministic_and_stable():
    offers = [make_offer(clinic="z", slot="1"), make_offer(clinic="a", slot="2")]
    assert rank(offers, make_request()) == rank(list(reversed(offers)), make_request())


def test_violations_dropped():
    r = make_request()
    offers = [make_offer(slot="ok"),
              make_offer(slot="early", hours=-5),
              make_offer(slot="late", hours=24 * 10),
              make_offer(slot="pricey", deposit=99),
              make_offer(slot="far", dist=50),
              make_offer(slot="ins", insurance_accepted=["Cigna"])]
    assert ids(rank(offers, r)) == ["ok"]
