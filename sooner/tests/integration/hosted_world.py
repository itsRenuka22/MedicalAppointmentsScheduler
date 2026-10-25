"""In-process model of the hosted deployment: same logic classes and Stores, direct calls instead
of Agentverse messaging. Every call counts as request + reply (2 messages)."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from sooner.agents.escrow_agent import EscrowLogic
from sooner.agents.matchmaker_agent import Matchmaker
from sooner.agents.patient_agent import PatientLogic
from sooner.core.clinic_host import ClinicHost
from sooner.core.registry import ProvisionError, Registry
from sooner.core.registry_chat import RegistryChat
from sooner.core.store import MemoryStore
from sooner.shared.models import ClinicEntry, SlotOffers

NOW = datetime(2026, 10, 25, 8, 0)
SEEDS = Path(__file__).resolve().parents[2] / "data" / "clinics.json"
LLM = lambda t: {"specialty": "dermatology", "days_ahead": 5, "insurance": "Aetna",
                 "max_deposit": 40, "radius_miles": 10}
NO_LLM = lambda t: (_ for _ in ()).throw(RuntimeError("no llm"))


class World:
    def __init__(self, max_dedicated=2, fail_provision=False):
        self.msgs, self.fail_provision = Counter(), fail_provision
        self.agents: dict[str, ClinicHost] = {"agent-hub": ClinicHost(MemoryStore())}
        self.escrow = EscrowLogic(MemoryStore())
        self.matchmaker = Matchmaker(MemoryStore(), timeout=0.5, list_timeout=0.5)
        self.registry = Registry(MemoryStore(), self, max_dedicated, "agent-hub")
        self.chat = RegistryChat(self.registry)
        self.pushed = []  # (patient_address, RankedOffers) the matchmaker pushed

    # Provisioner interface used by Registry
    def create_dedicated(self, record, profile):
        if self.fail_provision:
            raise ProvisionError("HTTP 402 quota exceeded")
        addr = f"agent-ded-{len(self.agents)}"
        self.agents[addr] = ClinicHost(MemoryStore())
        self.agents[addr].add_clinic(profile)
        return addr

    def delete(self, address):
        self.agents.pop(address, None)

    def seed(self):
        for c in json.loads(SEEDS.read_text())["clinics"]:
            res = self.registry.onboard(c, prefer_hub=True, now=NOW)
            assert res.ok, res.message
            self.agents["agent-hub"].add_clinic(res.profile)

    def register(self, owner, text):
        reply, res = self.chat.handle(owner, text, llm=NO_LLM, now=NOW)
        if res is not None and res.ok and res.hub_add:
            self.msgs["registry->hub"] += 2
            self.agents["agent-hub"].add_clinic(res.profile)
        return reply, res

    # --- wiring ----------------------------------------------------------------------
    async def list_clinics(self):
        self.msgs["matchmaker->registry"] += 2
        return [ClinicEntry(**{**r}) for r in (
            dict(clinic_id=e["clinic_id"], name=e["name"], address=e["address"], specialties=e["specialties"],
                 insurances=e["insurances"], host=e["host"], agent_address=e["agent_address"], status=e["status"])
            for e in self.registry.entries())]

    async def query(self, addr, req):
        self.msgs["matchmaker->clinic"] += 2
        return SlotOffers(request_id=req.request_id, offers=self.agents[addr].offers_for(req, now=NOW))

    def patient(self, user, store=None):
        store = store if store is not None else self.user_stores.setdefault(user, MemoryStore())

        async def ask(req):
            self.msgs["patient->matchmaker"] += 2
            return await self.matchmaker.search(req, self.list_clinics, self.query)

        async def book(addr, b):
            self.msgs["patient->clinic(book)"] += 2
            return self.agents[addr].book(b, now=NOW)

        async def pay(intent):
            self.msgs["patient->escrow"] += 2
            return self.escrow.handle_intent(intent)
        return PatientLogic(ask, book, pay, llm=LLM, now=NOW, address=user, store=store, sender=user)

    user_stores: dict = {}

    async def cancel(self, addr, clinic_id, slot_id):
        ev = self.agents[addr].cancel_booking(clinic_id, slot_id, now=NOW)
        if ev:
            self.msgs["clinic->matchmaker"] += 1
            for push in await self.matchmaker.on_cancellation(ev, self.list_clinics, self.query):
                self.pushed.append((push.patient_address, push))
        return ev
