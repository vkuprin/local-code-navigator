from notifications.channel import NotificationChannel


class EmailChannel(NotificationChannel):
    def deliver(self, recipient: str, body: str) -> bool:
        return "@" in recipient and bool(body)
