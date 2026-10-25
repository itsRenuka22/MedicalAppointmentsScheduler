"""EscrowAgent: holds the deposit, releases on confirmed booking, refunds on cancellation."""
from sooner.core.escrow import Escrow, EscrowError
from sooner.core.store import MemoryStore
from sooner.shared import config
from sooner.shared.models import PaymentIntent, PaymentReceipt

TESTNET_LABEL = "testnet-simulated"


class EscrowLogic:
    def __init__(self, store=None):
        self.store = store if store is not None else MemoryStore()
        self.escrow = Escrow(self.store)

    @property
    def by_booking(self) -> dict:
        return self.store.get("by_booking", {})

    def handle_intent(self, intent: PaymentIntent) -> PaymentReceipt:
        """pending -> hold; release / refund act on the existing hold."""
        bid = intent.booking_id
        if intent.status == "pending":
            if bid not in self.by_booking:
                self.store.set("by_booking", {**self.by_booking, bid: self.escrow.hold(intent.amount)})
        elif bid not in self.by_booking:
            raise EscrowError(f"no escrow for booking {bid}")
        eid = self.by_booking[bid]
        if intent.status == "release":
            self.escrow.release(eid)
        elif intent.status == "refund":
            self.escrow.refund(eid)
        return PaymentReceipt(booking_id=bid, amount=intent.amount,
                              status=self.escrow.status(eid), tx_ref=f"{TESTNET_LABEL}:{eid}")


def build_agent():
    from uagents import Agent, Context, Protocol
    from uagents_core.contrib.protocols.payment import (CommitPayment, CompletePayment,
                                                        RejectPayment, payment_protocol_spec)
    agent = Agent(name="escrow", seed=config.seed("escrow"), port=config.PORTS["escrow"],
                  endpoint=[f"http://127.0.0.1:{config.PORTS['escrow']}/submit"])
    logic = EscrowLogic()

    @agent.on_message(PaymentIntent, replies={PaymentReceipt})
    async def on_intent(ctx: Context, sender: str, msg: PaymentIntent):
        try:
            await ctx.send(sender, logic.handle_intent(msg))
        except EscrowError as e:
            ctx.logger.warning(str(e))

    # Agent Payment Protocol: a wallet-side CommitPayment places the deposit hold.
    payments = Protocol(spec=payment_protocol_spec, role="seller")

    @payments.on_message(CommitPayment)
    async def on_commit(ctx: Context, sender: str, msg: CommitPayment):
        ref = msg.reference or msg.transaction_id
        logic.handle_intent(PaymentIntent(booking_id=ref, amount=float(msg.funds.amount)))
        await ctx.send(sender, CompletePayment(transaction_id=msg.transaction_id))

    @payments.on_message(RejectPayment)
    async def on_reject(ctx: Context, sender: str, msg: RejectPayment):
        ctx.logger.info(f"payment rejected: {msg.reason}")

    agent.include(payments, publish_manifest=True)
    agent.logic = logic
    return agent
