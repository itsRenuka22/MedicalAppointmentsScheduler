import pytest
from sooner.core.escrow import Escrow, EscrowError


def test_release_idempotent():
    e = Escrow(); i = e.hold(10)
    assert e.release(i) == e.release(i) == "released"


def test_refund_idempotent():
    e = Escrow(); i = e.hold(10)
    assert e.refund(i) == e.refund(i) == "refunded"


def test_cannot_release_refunded():
    e = Escrow(); i = e.hold(10); e.refund(i)
    with pytest.raises(EscrowError):
        e.release(i)


def test_cannot_refund_released():
    e = Escrow(); i = e.hold(10); e.release(i)
    with pytest.raises(EscrowError):
        e.refund(i)


def test_invalid_amount_and_unknown_id():
    e = Escrow()
    with pytest.raises(EscrowError):
        e.hold(0)
    with pytest.raises(EscrowError):
        e.release("nope")
