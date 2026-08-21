from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Dict, Any

# Callback type for emitting incoming messages to the orchestrator:
# callback(channel, sender, text, msg_uid)
MessageCallback = Callable[[str, str, str, str], Awaitable[None]]

class BaseAdapter(ABC):
    def __init__(self, name: str):
        self.name = name
        self._callback: MessageCallback = None

    def set_callback(self, callback: MessageCallback):
        self._callback = callback

    async def emit_message(self, sender: str, text: str, msg_uid: str):
        if self._callback:
            await self._callback(self.name, sender, text, msg_uid)

    @abstractmethod
    async def start(self):
        """Starts listening for incoming messages."""
        pass

    @abstractmethod
    async def stop(self):
        """Stops the adapter gracefully."""
        pass
