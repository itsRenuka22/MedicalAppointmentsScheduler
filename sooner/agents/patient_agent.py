"""PatientAgent: ASI:One-facing chat agent. Books and pays only on an explicit card tap."""
from pathlib import Path
from typing import Awaitable, Callable, Optional

from sooner.agents.intent import parse_intent
from sooner.cards.interactive_cards import offers_cards, render_text, resolve_choice
from sooner.shared.config import SYNTHETIC_NOTICE
from sooner.shared.models import (BookingRequest, BookingResult, LatLng, PaymentIntent,
                                  PaymentReceipt, RankedOffers, SlotOffer, SlotRequest)


class PatientLogic:
    def __init__(self, ask_matchmaker: Callable[[SlotRequest], Awaitable[RankedOffers]],
                 book: Callable[[str, BookingRequest], Awaitable[BookingResult]],
                 pay: Callable[[PaymentIntent], Awaitable[PaymentReceipt]],
                 location: LatLng = LatLng(lat=37.7946, lng=-122.3950),
                 address: str = "1 Demo Way, San Francisco, CA", llm=None, now=None, store=None, sender: str = ""):
        self.ask_matchmaker, self.book, self.pay = ask_matchmaker, book, pay
        self.location, self.address, self.llm, self.now = location, address, llm, now
        self.store, self.sender = store, sender
        self.offers: dict = {}  # (clinic_id, slot_id) -> SlotOffer, in ranked order
        if store is not None:  # offers survive between messages (hosted agents keep no globals)
            for raw in store.get(f"offers:{sender}", []):
                o = SlotOffer.parse_raw(raw)
                self.offers[(o.clinic_id, o.slot_id)] = o

    def _remember(self, offers) -> None:
        self.offers = {(o.clinic_id, o.slot_id): o for o in offers}
        if self.store is not None:
            self.store.set(f"offers:{self.sender}", [o.json() for o in offers])

    def accept_reoffer(self, ranked: RankedOffers) -> str:
        """A cancelled slot matched a waiting search: remember the offers and tell the user."""
        self._remember(ranked.offers)
        return "A slot just opened up!\n" + render_text(offers_cards(ranked.offers)) + "\nReply 'book 1' to take it."

    async def handle_message(self, text: str) -> str:
        choice = resolve_choice(text, list(self.offers.values()))
        if choice is None:
            return await self._search(text)
        if not self.offers:
            return "I have no offers for you yet. Please search first, e.g. 'dermatologist, Aetna'."
        if choice == "ambiguous":
            return "That matches more than one clinic. Reply with the number, e.g. 'book 1'."
        if choice == "unknown":
            return "I couldn't find that offer. Reply with a number from the list, e.g. 'book 1'."
        return await self._confirm(*choice)

    async def _search(self, text: str) -> str:
        req = parse_intent(text, self.location, self.address, now=self.now, llm=self.llm)
        ranked = await self.ask_matchmaker(req)  # shows whatever arrived before the timeout
        self._remember(ranked.offers)
        return render_text(offers_cards(ranked.offers)) + (
            "\nReply 'book 1' (or 'book <clinic name>') to book." if ranked.offers else "")

    async def _confirm(self, clinic_id: str, slot_id: str) -> str:
        offer = self.offers.get((clinic_id, slot_id))
        if offer is None:
            return "That offer is no longer available. Please search again."
        booking_id = f"{offer.request_id}-{slot_id}"
        receipt = await self.pay(PaymentIntent(booking_id=booking_id, amount=offer.deposit))
        result = await self.book(offer.agent_address or clinic_id, BookingRequest(
            request_id=offer.request_id, clinic_id=clinic_id, slot_id=slot_id,
            patient_address=self.address, expected_version=offer.slot_version))
        if result.ok:
            await self.pay(PaymentIntent(booking_id=booking_id, amount=offer.deposit, status="release"))
            return (f"Booked {offer.clinic_name} at {offer.slot_time:%a %b %d %I:%M %p}. "
                    f"Confirmation {result.confirmation_id}. Deposit ${offer.deposit:.2f} (simulated) "
                    f"released to clinic (tx {receipt.tx_ref}). {SYNTHETIC_NOTICE}")
        await self.pay(PaymentIntent(booking_id=booking_id, amount=offer.deposit, status="refund"))
        self.offers.pop((clinic_id, slot_id), None)
        self._remember(list(self.offers.values()))
        return (f"Sorry, that slot was just taken ({result.reason}). Your deposit was refunded. "
                "Try another offer or search again.")


def build_agent(matchmaker_address: str, escrow_address: str, clinic_addresses: dict[str, str]):
    """Wires PatientLogic to real agent messaging via ctx.send_and_receive and the Chat Protocol."""
    from datetime import datetime, timezone
    from uagents import Agent, Context, Protocol
    from uagents_core.contrib.protocols.chat import (ChatAcknowledgement, ChatMessage,
                                                     TextContent, chat_protocol_spec)
    from sooner.shared import config

    agent = Agent(name="sooner_patient", seed=config.seed("patient"), port=config.PORTS["patient"],
                  mailbox=True, publish_agent_details=True,
                  readme_path=str(Path(__file__).with_name("patient_README.md")))
    chat = Protocol(spec=chat_protocol_spec)
    sessions: dict[str, PatientLogic] = {}

    @chat.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    @chat.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))

        async def send_recv(addr, payload, model):
            reply, status = await ctx.send_and_receive(addr, payload, response_type=model, timeout=10)
            if reply is None:
                raise RuntimeError(f"no reply: {status}")
            return reply

        logic = sessions.get(sender)
        if logic is None:  # one PatientLogic per chat so offers survive until the card tap
            logic = sessions[sender] = PatientLogic(
                lambda r: send_recv(matchmaker_address, r, RankedOffers),
                lambda cid, b: send_recv(clinic_addresses[cid], b, BookingResult),
                lambda p: send_recv(escrow_address, p, PaymentReceipt))
        try:
            reply = await logic.handle_message(msg.text())
        except Exception as e:  # always answer the chat instead of leaving it hanging
            ctx.logger.exception("handler failed")
            reply = f"Sorry, something went wrong ({type(e).__name__}). Please try again."
        await ctx.send(sender, ChatMessage(content=[TextContent(type="text", text=reply)]))

    agent.include(chat, publish_manifest=True)
    return agent


def main():
    """Standalone entry point: python -m sooner.agents.patient_agent (Bureau runs the rest)."""
    from sooner.shared.config import CLINIC_IDS, agent_address, ensure_event_loop
    ensure_event_loop()
    agent = build_agent(agent_address("matchmaker"), agent_address("escrow"),
                        {cid: agent_address(cid) for cid in CLINIC_IDS})
    print(SYNTHETIC_NOTICE)
    print(f"sooner_patient address: {agent.address}")
    agent.run()


if __name__ == "__main__":
    main()
