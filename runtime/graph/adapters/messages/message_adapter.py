from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from runtime.contracts import Message


class MessageAdapter(ABC):
    """
    Converts between domain messages and framework messages.
    """

    @abstractmethod
    def to_framework(
        self,
        message: Message,
    ):
        ...

    @abstractmethod
    def from_framework(
        self,
        message,
    ) -> Message:
        ...

    @abstractmethod
    def to_framework_messages(
        self,
        messages: list[Message],
    ):
        ...

    @abstractmethod
    def from_framework_messages(
        self,
        messages,
    ) -> list[Message]:
        ...