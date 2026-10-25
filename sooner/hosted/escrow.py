"""Hosted EscrowAgent: simulated deposit hold / release / refund, persisted in agent storage."""
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.payment import (CommitPayment, CompletePayment, RejectPayment,
                                                    payment_protocol_spec)

from sooner.agents.escrow_agent import EscrowLogic
from sooner.core.escrow import EscrowError
from sooner.core.store import CtxStore
from sooner.shared.models import PaymentIntent, PaymentReceipt

agent = Agent()


@agent.on_message(PaymentIntent, replies={PaymentReceipt})
async def on_intent(ctx: Context, sender: str, msg: PaymentIntent):
    try:
        await ctx.send(sender, EscrowLogic(CtxStore(ctx.storage)).handle_intent(msg))
    except EscrowError as e:
        ctx.logger.warning(str(e))


payments = Protocol(spec=payment_protocol_spec, role="seller")


@payments.on_message(CommitPayment)
async def on_commit(ctx: Context, sender: str, msg: CommitPayment):
    ref = msg.reference or msg.transaction_id
    EscrowLogic(CtxStore(ctx.storage)).handle_intent(PaymentIntent(booking_id=ref, amount=float(msg.funds.amount)))
    await ctx.send(sender, CompletePayment(transaction_id=msg.transaction_id))


@payments.on_message(RejectPayment)
async def on_reject(ctx: Context, sender: str, msg: RejectPayment):
    ctx.logger.info("payment rejected")


agent.include(payments, publish_manifest=True)
