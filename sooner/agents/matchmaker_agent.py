"""MatchmakerAgent: discover clinics, broadcast, collect with a timeout, rank."""
import asyncio
import json
from typing import Awaitable, Callable, Optional

from sooner.core.ranking import rank
from sooner.shared import config
from sooner.core.store import MemoryStore, Store
from sooner.shared.models import (CancellationEvent, ClinicEntry, RankedOffers, SlotOffer, SlotOffers,
                                  SlotRequest)
from sooner.shared.resilience import call_with_retry

ClinicQuery = Callable[[SlotRequest], Awaitable[Optional[SlotOffer]]]


def discover_clinics(request: SlotRequest, registry: dict[str, ClinicQuery]) -> list[ClinicQuery]:
    """Return the clinic endpoints to query. The registry is populated from Agentverse
    search results (or the static config in local dev); specialty/location filtering is
    also enforced by each clinic on receipt, so over-inclusion here is harmless."""
    return list(registry.values())


async def gather_offers(request: SlotRequest, queries: list[ClinicQuery],
                        timeout: float = config.OFFER_TIMEOUT_S) -> list[SlotOffer]:
    """Broadcast, keep what arrives before the timeout, drop late or failed replies."""
    tasks = [asyncio.create_task(call_with_retry(lambda q=q: q(request), retries=config.RETRIES,
                                                 delay=config.RETRY_DELAY_S)) for q in queries]
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for t in pending:
        t.cancel()  # late replies are dropped
    return [t.result() for t in done if not t.cancelled() and t.result() is not None]


async def handle_slot_request(request: SlotRequest, registry: dict[str, ClinicQuery],
                              timeout: float = config.OFFER_TIMEOUT_S) -> RankedOffers:
    offers = await gather_offers(request, discover_clinics(request, registry), timeout)
    return RankedOffers(request_id=request.request_id, offers=rank(offers, request))


WAITLIST_MAX = 10
ListClinics = Callable[[], Awaitable[Optional[list]]]
QueryAgent = Callable[[str, SlotRequest], Awaitable[Optional[SlotOffers]]]


class Matchmaker:
    """Registry-driven search. One query per serving agent (the hub answers for many clinics),
    clinics that cannot match are never contacted, and empty searches wait for cancellations."""

    def __init__(self, store: Optional[Store] = None, timeout: float = config.OFFER_TIMEOUT_S,
                 list_timeout: float = 3.0):
        self.store = store if store is not None else MemoryStore()
        self.timeout, self.list_timeout = timeout, list_timeout

    async def _clinics(self, list_clinics: ListClinics) -> list[ClinicEntry]:
        try:
            got = await asyncio.wait_for(list_clinics(), self.list_timeout)
        except Exception:
            got = None
        if got is not None:
            self.store.set("known_clinics", [json.loads(c.json()) for c in got])
        return [ClinicEntry.parse_obj(c) for c in self.store.get("known_clinics", [])]

    @staticmethod
    def _can_match(c: ClinicEntry, req: SlotRequest) -> bool:
        return (c.status == "active" and req.specialty.lower() in [s.lower() for s in c.specialties]
                and req.insurance in c.insurances)

    async def _fan_out(self, req: SlotRequest, clinics: list[ClinicEntry], query: QueryAgent):
        groups: dict[str, list[str]] = {}
        for c in clinics:
            if self._can_match(c, req) and c.agent_address:
                groups.setdefault(c.agent_address, []).append(c.clinic_id)

        async def ask(addr, ids):
            r = SlotRequest(**{**json.loads(req.json()), "clinic_ids": ids})
            res = await query(addr, r)
            if res is not None:
                for o in res.offers:
                    o.agent_address = addr
            return res

        tasks = [asyncio.create_task(call_with_retry(lambda a=a, i=i: ask(a, i), retries=config.RETRIES,
                                                     delay=config.RETRY_DELAY_S)) for a, i in groups.items()]
        if not tasks:
            return []
        done, pending = await asyncio.wait(tasks, timeout=self.timeout)
        for t in pending:
            t.cancel()  # late or dead agents are dropped
        return [o for t in done if not t.cancelled() and t.result() is not None for o in t.result().offers]

    async def search(self, req: SlotRequest, list_clinics: ListClinics, query: QueryAgent) -> RankedOffers:
        offers = await self._fan_out(req, await self._clinics(list_clinics), query)
        ranked = RankedOffers(request_id=req.request_id, offers=rank(offers, req))
        if not ranked.offers and req.patient_address:
            wl = [w for w in self.store.get("waitlist", []) if json.loads(w)["patient_address"] != req.patient_address]
            self.store.set("waitlist", (wl + [req.json()])[-WAITLIST_MAX:])
        return ranked

    async def on_cancellation(self, event: CancellationEvent, list_clinics: ListClinics,
                              query: QueryAgent) -> list[RankedOffers]:
        """A slot was freed: re-run waiting searches against that clinic and push any matches."""
        clinics = [c for c in await self._clinics(list_clinics) if c.clinic_id == event.clinic_id]
        pushes, still_waiting = [], []
        for raw in self.store.get("waitlist", []):
            req = SlotRequest.parse_raw(raw)
            offers = rank(await self._fan_out(req, clinics, query), req)
            if offers:
                pushes.append(RankedOffers(request_id=req.request_id, offers=offers,
                                           patient_address=req.patient_address))
            else:
                still_waiting.append(raw)
        self.store.set("waitlist", still_waiting)
        return pushes


def build_agent(clinic_addresses: dict[str, str]):
    from uagents import Agent, Context
    agent = Agent(name="sooner_matchmaker", seed=config.seed("matchmaker"),
                  port=config.PORTS["matchmaker"],
                  endpoint=[f"http://127.0.0.1:{config.PORTS['matchmaker']}/submit"])

    @agent.on_message(SlotRequest, replies={RankedOffers})
    async def on_request(ctx: Context, sender: str, msg: SlotRequest):
        def query(addr):
            async def q(req):
                reply, _ = await ctx.send_and_receive(addr, req, response_type=SlotOffer, timeout=5)
                return reply
            return q
        registry = {cid: query(addr) for cid, addr in clinic_addresses.items()}
        await ctx.send(sender, await handle_slot_request(msg, registry))

    return agent
