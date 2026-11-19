"""Helper for asserting how many coroutines ran at the same time."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class PeakTracker:
    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    def wrap(
        self, result: Callable[..., Any], hold_s: float = 0.02
    ) -> Callable[..., Awaitable[Any]]:
        """Async stand-in that stays 'in flight' for hold_s, then returns."""

        async def fake(*args: Any, **kwargs: Any) -> Any:
            self.current += 1
            self.peak = max(self.peak, self.current)
            try:
                await asyncio.sleep(hold_s)
                return result(*args, **kwargs)
            finally:
                self.current -= 1

        return fake
