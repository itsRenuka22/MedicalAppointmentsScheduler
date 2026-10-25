"""Hosted PatientAgent: the ASI:One front door. Chat Protocol, offers kept per sender in storage."""
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, chat_protocol_spec

from deploy_config import ADDRESSES
from sooner.agents.patient_agent import PatientLogic
from sooner.core.store import CtxStore
from sooner.hosted.chat_util import ack, ask, text_message
from sooner.shared.models import BookingResult, PaymentReceipt, RankedOffers

agent = Agent()
chat = Protocol(spec=chat_protocol_spec)


def logic_for(ctx: Context, sender: str) -> PatientLogic:
    return PatientLogic(
        lambda req: ask(ctx, ADDRESSES["matchmaker"], req, RankedOffers, 25),
        lambda addr, b: ask(ctx, addr, b, BookingResult, 10),
        lambda intent: ask(ctx, ADDRESSES["escrow"], intent, PaymentReceipt, 10),
        address=sender, store=CtxStore(ctx.storage), sender=sender)


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ack(ctx, sender, msg)
    try:
        reply = await logic_for(ctx, sender).handle_message(msg.text())
    except Exception as e:  # always answer the chat instead of leaving it hanging
        ctx.logger.error(f"handler failed: {type(e).__name__}")
        reply = f"Sorry, something went wrong ({type(e).__name__}). Please try again."
    await ctx.send(sender, text_message(reply))


@agent.on_message(RankedOffers)
async def on_push(ctx: Context, sender: str, msg: RankedOffers):
    """Unsolicited re-offer from the matchmaker after a cancellation."""
    if msg.patient_address:
        await ctx.send(msg.patient_address, text_message(logic_for(ctx, msg.patient_address).accept_reoffer(msg)))


agent.include(chat, publish_manifest=True)
