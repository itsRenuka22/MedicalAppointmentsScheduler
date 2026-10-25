"""Chat Protocol helpers shared by every hosted agent that talks to ASI:One."""
from datetime import datetime, timezone
from uuid import uuid4

from uagents import Context
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, TextContent


async def ack(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc),
                                               acknowledged_msg_id=msg.msg_id))


def text_message(text: str) -> ChatMessage:
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                       content=[TextContent(type="text", text=text)])


async def ask(ctx: Context, address: str, message, response_type, timeout: float = 10):
    """send_and_receive that raises instead of returning (None, status)."""
    reply, status = await ctx.send_and_receive(address, message, response_type=response_type, timeout=timeout)
    if reply is None:
        raise RuntimeError(f"no reply from {address[:12]}: {status}")
    return reply
