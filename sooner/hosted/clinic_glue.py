"""Message handlers shared by the dedicated clinic agent and the clinic hub."""
from typing import Callable

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, chat_protocol_spec

from sooner.core.clinic_host import ClinicHost
from sooner.core.store import CtxStore
from sooner.hosted.chat_util import ack, text_message
from sooner.shared.models import (BookingRequest, BookingResult, CancellationEvent, SlotOffers,
                                  SlotRequest)


def attach(agent: Agent, matchmaker_address: str, host_for: Callable[[Context], ClinicHost],
           split_command: Callable[[ClinicHost, str], tuple]) -> Protocol:
    """Wire SlotRequest / BookingRequest / chat management onto `agent`.
    split_command(host, text) -> (clinic_id, command_text) or (None, error_text)."""

    @agent.on_message(SlotRequest, replies={SlotOffers})
    async def on_request(ctx: Context, sender: str, msg: SlotRequest):
        await ctx.send(sender, SlotOffers(request_id=msg.request_id, offers=host_for(ctx).offers_for(msg)))

    @agent.on_message(BookingRequest, replies={BookingResult})
    async def on_booking(ctx: Context, sender: str, msg: BookingRequest):
        await ctx.send(sender, host_for(ctx).book(msg))

    chat = Protocol(spec=chat_protocol_spec)

    @chat.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    @chat.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ack(ctx, sender, msg)
        host = host_for(ctx)
        clinic_id, command = split_command(host, msg.text())
        if clinic_id is None:
            reply, event = command, None
        else:
            reply, event = host.handle_command(clinic_id, sender, command)
        await ctx.send(sender, text_message(reply))
        if event is not None and matchmaker_address:
            await ctx.send(matchmaker_address, event)  # waiting patients get the freed slot

    agent.include(chat, publish_manifest=True)
    return chat
