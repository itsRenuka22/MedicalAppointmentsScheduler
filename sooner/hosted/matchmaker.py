"""Hosted MatchmakerAgent: asks the Registry for clinics, fans out one query per serving agent."""
from uagents import Agent, Context

from deploy_config import ADDRESSES
from sooner.agents.matchmaker_agent import Matchmaker
from sooner.core.store import CtxStore
from sooner.hosted.chat_util import ask
from sooner.shared.models import (CancellationEvent, ClinicListRequest, ClinicListResponse,
                                  RankedOffers, SlotOffers, SlotRequest)

agent = Agent()


def _io(ctx: Context):
    async def list_clinics():
        return (await ask(ctx, ADDRESSES["registry"], ClinicListRequest(), ClinicListResponse, 5)).clinics

    async def query(addr, req):
        return await ask(ctx, addr, req, SlotOffers, 6)
    return list_clinics, query


@agent.on_message(SlotRequest, replies={RankedOffers})
async def on_request(ctx: Context, sender: str, msg: SlotRequest):
    list_clinics, query = _io(ctx)
    await ctx.send(sender, await Matchmaker(CtxStore(ctx.storage)).search(msg, list_clinics, query))


@agent.on_message(CancellationEvent)
async def on_cancellation(ctx: Context, sender: str, msg: CancellationEvent):
    list_clinics, query = _io(ctx)
    for push in await Matchmaker(CtxStore(ctx.storage)).on_cancellation(msg, list_clinics, query):
        await ctx.send(ADDRESSES["patient"], push)  # the patient agent relays it to the user's chat
