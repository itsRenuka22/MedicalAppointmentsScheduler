"""Clinic hub: hosts several clinics in one hosted agent, routing by clinic_id."""
import json

from uagents import Agent, Context

from deploy_config import ADDRESSES
from sooner.core.clinic_host import ClinicHost
from sooner.core.store import CtxStore
from sooner.hosted.clinic_glue import attach
from sooner.shared.models import HubAddClinic, HubAddResult

agent = Agent()


def host_for(ctx: Context) -> ClinicHost:
    return ClinicHost(CtxStore(ctx.storage))


def split_command(host: ClinicHost, text: str):
    """Hub chat commands are addressed: '<clinic_id>: add slot 2026-10-28T10:00 150'."""
    head, sep, rest = text.partition(":")
    cid = head.strip()
    if sep and host.profile(cid) is not None:
        return cid, rest.strip()
    return None, "Start with the clinic id, e.g. '<clinic_id>: list slots'. Hosted: " + ", ".join(host.clinic_ids())


@agent.on_message(HubAddClinic, replies={HubAddResult})
async def on_add(ctx: Context, sender: str, msg: HubAddClinic):
    profile = json.loads(msg.profile_json)
    try:
        host_for(ctx).add_clinic(profile)
        await ctx.send(sender, HubAddResult(clinic_id=profile["clinic_id"], ok=True))
    except Exception as e:
        await ctx.send(sender, HubAddResult(clinic_id=profile.get("clinic_id", ""), ok=False, detail=str(e)[:120]))


attach(agent, ADDRESSES.get("matchmaker", ""), host_for, split_command)
