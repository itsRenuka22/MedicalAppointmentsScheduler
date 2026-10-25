"""Hosted RegistryAgent: clinic onboarding over chat, and the clinic list for the matchmaker."""
import json
import os

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, chat_protocol_spec

from clinic_bundle import CLINIC_CONFIG_MODULE, CLINIC_FILES, CLINIC_README
from deploy_config import ADDRESSES, MAX_DEDICATED_CLINIC_AGENTS
from sooner.core.registry import Registry
from sooner.core.registry_chat import RegistryChat
from sooner.core.store import CtxStore
from sooner.hosted.chat_util import ack, text_message
from sooner.shared.hosting_api import HostedProvisioner, HostingClient
from sooner.shared.models import (ClinicEntry, ClinicListRequest, ClinicListResponse, HubAddClinic,
                                  HubAddResult, RegisterClinic, RegisterClinicResult)

agent = Agent()
chat = Protocol(spec=chat_protocol_spec)


def registry_for(ctx: Context) -> Registry:
    prov = HostedProvisioner(HostingClient(os.getenv("AGENTVERSE_API_KEY", "")), CLINIC_FILES,
                             {}, CLINIC_CONFIG_MODULE, CLINIC_README)
    return Registry(CtxStore(ctx.storage), prov, MAX_DEDICATED_CLINIC_AGENTS, ADDRESSES["clinic_hub"])


async def _after(ctx: Context, result) -> None:
    if result is not None and result.ok and result.hub_add:
        await ctx.send(ADDRESSES["clinic_hub"], HubAddClinic(profile_json=json.dumps(result.profile)))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ack(ctx, sender, msg)
    try:
        reply, result = RegistryChat(registry_for(ctx)).handle(sender, msg.text())
        await _after(ctx, result)
    except Exception as e:
        ctx.logger.error(f"onboarding failed: {type(e).__name__}")
        reply = f"Sorry, something went wrong ({type(e).__name__}). Please try again."
    await ctx.send(sender, text_message(reply))


@agent.on_message(RegisterClinic, replies={RegisterClinicResult})
async def on_register(ctx: Context, sender: str, msg: RegisterClinic):
    """Structured onboarding through the same path as chat (used to seed the demo clinics)."""
    res = registry_for(ctx).onboard(json.loads(msg.profile_json), prefer_hub=msg.prefer_hub, owner="")
    await _after(ctx, res)
    await ctx.send(sender, RegisterClinicResult(ok=res.ok, clinic_id=res.clinic_id, host=res.host,
                                                agent_address=res.agent_address, message=res.message))


@agent.on_message(ClinicListRequest, replies={ClinicListResponse})
async def on_list(ctx: Context, sender: str, msg: ClinicListRequest):
    entries = [ClinicEntry(clinic_id=r["clinic_id"], name=r["name"], address=r["address"],
                           specialties=r["specialties"], insurances=r["insurances"], host=r["host"],
                           agent_address=r["agent_address"], status=r["status"])
               for r in registry_for(ctx).entries()]
    await ctx.send(sender, ClinicListResponse(clinics=entries))


@agent.on_message(HubAddResult)
async def on_hub_result(ctx: Context, sender: str, msg: HubAddResult):
    if not msg.ok:  # half-created: keep it out of search
        registry_for(ctx).set_status(msg.clinic_id, "unavailable")


agent.include(chat, publish_manifest=True)
