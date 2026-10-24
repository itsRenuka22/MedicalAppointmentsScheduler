"""MatchmakerAgent: discover clinics, broadcast, collect with a timeout, rank."""
import asyncio
from typing import Awaitable, Callable, Optional

from sooner.core.ranking import rank
from sooner.shared import config
from sooner.shared.models import RankedOffers, SlotOffer, SlotRequest
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
