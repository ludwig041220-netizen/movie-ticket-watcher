from __future__ import annotations

from dataclasses import dataclass


class NotificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Message:
    subject: str
    text: str
    html: str


class BaseNotifier:
    name = "notifier"

    def send(self, message: Message) -> None:
        raise NotImplementedError

