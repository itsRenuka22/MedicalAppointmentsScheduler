from datetime import datetime

"""In-process world: real handlers wired directly, no network."""
from sooner.agents.clinic_agent import ClinicLogic
from sooner.agents.escrow_agent import EscrowLogic
from sooner.agents.matchmaker_agent import handle_slot_request
from sooner.agents.patient_agent import PatientLogic
from sooner.cards.interactive_cards import BOOK_PREFIX
from sooner.core.policy import load_clinics


class World:
    def __init__(self, timeout: float = 1.0):
        self.logics = {cid: ClinicLogic(c) for cid, c in load_clinics().items()}
        self.escrow = EscrowLogic()
        self.timeout = timeout

    def _query(self, logic):
        async def q(req):
            return logic.handle_slot_request(req)
        return q

    def patient(self, llm=None) -> PatientLogic:
        registry = {cid: self._query(l) for cid, l in self.logics.items()}

        async def ask(req):
            return await handle_slot_request(req, registry, self.timeout)

        async def book(cid, b):
            return self.logics[cid].handle_booking(b)

        async def pay(intent):
            return self.escrow.handle_intent(intent)
        return PatientLogic(ask, book, pay, llm=llm, now=datetime(2026, 10, 25, 8, 0))

    @staticmethod
    def first_tap(p: PatientLogic) -> str:
        cid, sid = next(iter(p.offers))
        return f"{BOOK_PREFIX}{cid}:{sid}"
