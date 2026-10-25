"""Send one chat request to the running patient agent and print its reply.
Usage: python -m sooner.scripts.test_patient ["request text"]"""
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from uagents import Agent, Context
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, TextContent

from sooner.shared import config

TEXT = sys.argv[1] if len(sys.argv) > 1 else "I need a dermatologist, Aetna, deposit under $40"
STARTED = time.monotonic()
PATIENT = config.agent_address("patient")

config.ensure_event_loop()
client = Agent(name="sooner_test_client", seed="sooner-test-client-seed", port=8300,
               endpoint=["http://127.0.0.1:8300/submit"])


@client.on_event("startup")
async def send(ctx: Context):
    print(f"-> patient {PATIENT}\n   {TEXT!r}")
    await ctx.send(PATIENT, ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                                        content=[TextContent(type="text", text=TEXT)]))


@client.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    print("<- ack from patient (patient received the request)")


@client.on_message(ChatMessage)
async def on_reply(ctx: Context, sender: str, msg: ChatMessage):
    print("<- reply from patient:\n" + msg.text())
    raise SystemExit(0)


@client.on_interval(period=5)
async def give_up(ctx: Context):
    if time.monotonic() - STARTED > 90:  # on_interval also fires once at startup
        print("!! no reply within 90s")
        raise SystemExit(1)


if __name__ == "__main__":
    client.run()
