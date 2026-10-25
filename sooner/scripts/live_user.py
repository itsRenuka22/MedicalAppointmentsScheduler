"""A scripted chat user for the live (hosted) deployment. Registers itself as a mailbox agent via
the API key (no Inspector click), runs JSON steps, prints one JSON line per result.
Usage: python -m sooner.scripts.live_user <steps.json> <seed>"""
import asyncio
import json
import os
import re
import sys
import time

from uagents import Agent, Context
from uagents.config import AgentverseConfig
from uagents.mailbox import AgentverseConnectRequest, register_in_agentverse
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, TextContent
from uagents_core.registration import AgentEndpoint, RegistrationRequest

from sooner.scripts.env import load_env
from sooner.shared.models import RegisterClinic, RegisterClinicResult

load_env()


def emit(label: str, text: str) -> None:
    print(json.dumps({"label": label, "text": text, "t": round(time.time(), 1)}), flush=True)


def main(steps_path: str, seed: str) -> None:
    from datetime import datetime, timezone
    from uuid import uuid4
    asyncio.set_event_loop(asyncio.new_event_loop())
    steps = json.load(open(steps_path))
    import hashlib
    port = 8300 + int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 500  # one process per seed; avoid port clashes
    user = Agent(name="sooner_live_" + seed[-6:], seed=seed, mailbox=True, port=port)
    chats: asyncio.Queue = asyncio.Queue()
    results: asyncio.Queue = asyncio.Queue()
    state = {"last": "", "labels": {}}

    @user.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await chats.put(msg.text())

    @user.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    @user.on_message(RegisterClinicResult)
    async def on_result(ctx: Context, sender: str, msg: RegisterClinicResult):
        await results.put(msg)

    async def next_chat(timeout: float, contains: str = "") -> str:
        """Next chat message (optionally one containing `contains`; others are dropped)."""
        deadline = time.time() + timeout
        while True:
            text = await asyncio.wait_for(chats.get(), max(1, deadline - time.time()))
            if not contains or contains in text:
                return text

    def cleanup() -> None:
        """Free this identity's slot in the account's agent quota."""
        import requests
        try:
            requests.delete(f"https://agentverse.ai/v1/agents/{user.address}", timeout=15,
                            headers={"Authorization": "Bearer " + os.environ["AGENTVERSE_API_KEY"]})
        except Exception:
            pass

    async def run_steps(ctx: Context, steps: list) -> None:
        for st in steps:
            op = st["op"]
            if op == "sleep_until":
                await asyncio.sleep(max(0, st["epoch"] - time.time()))
            elif op == "chat":
                while not chats.empty():  # drop stale mailbox deliveries from earlier runs of this identity
                    chats.get_nowait()
                to = st.get("to")
                if st.get("to_from"):
                    to = re.search(st["to_from"]["regex"], state["labels"][st["to_from"]["label"]]).group(1)
                await ctx.send(to, ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                                               content=[TextContent(type="text", text=st["text"])]))
                state["last"] = await next_chat(st.get("timeout", 60), st.get("contains", ""))
                state["labels"][st["label"]] = state["last"]
                emit(st["label"], state["last"])
            elif op == "wait_chat":
                state["last"] = await next_chat(st.get("timeout", 90), st.get("contains", ""))
                state["labels"][st["label"]] = state["last"]
                emit(st["label"], state["last"])
            elif op == "register":
                await ctx.send(st["to"], RegisterClinic(profile_json=json.dumps(st["profile"]),
                                                        prefer_hub=st.get("prefer_hub", False)))
                r = await asyncio.wait_for(results.get(), st.get("timeout", 90))
                emit(st["label"], f"ok={r.ok} host={r.host} {r.message}")
            elif op == "if_last_contains":
                if st["text"] in state["labels"].get(st.get("label"), state["last"]):
                    await run_steps(ctx, st["then"])
            elif op == "sleep":
                await asyncio.sleep(st["seconds"])

    @user.on_event("startup")
    async def go(ctx: Context):
        av = AgentverseConfig()
        res = await register_in_agentverse(
            AgentverseConnectRequest(user_token=os.environ["AGENTVERSE_API_KEY"], agent_type="mailbox"),
            user._identity, "agent", av,
            RegistrationRequest(address=user.address, name=user._name[:32], agent_type="mailbox",
                                endpoints=[AgentEndpoint(url=av.mailbox_endpoint, weight=1)], protocols=[]))
        if not res.success:
            emit("error", f"mailbox registration failed: {res.detail}")
            os._exit(1)
        emit("address", user.address)
        await asyncio.sleep(4)  # let the mailbox client connect
        try:
            await run_steps(ctx, steps)
        except Exception as e:
            emit("error", f"{type(e).__name__}: {e}")
        cleanup()
        emit("cleanup", "mailbox identity removed from the account")
        os._exit(0)

    user.run()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
