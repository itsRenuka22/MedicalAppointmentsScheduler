"""Timeouts and retries so one slow or dead clinic never breaks a search."""
import asyncio
from typing import Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


async def call_with_retry(fn: Callable[[], Awaitable[T]], retries: int = 2,
                          delay: float = 0.2, timeout: Optional[float] = None) -> Optional[T]:
    """Run fn up to retries+1 times; return None if every attempt fails or times out."""
    for attempt in range(retries + 1):
        try:
            coro = fn()
            return await (asyncio.wait_for(coro, timeout) if timeout else coro)
        except Exception:  # includes asyncio.TimeoutError
            if attempt < retries:
                await asyncio.sleep(delay)
    return None
