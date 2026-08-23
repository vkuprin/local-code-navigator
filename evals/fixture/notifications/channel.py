"""Notification channel protocol."""

from typing import Protocol


class NotificationChannel(Protocol):
    def deliver(self, recipient: str, body: str) -> bool:
        ...
