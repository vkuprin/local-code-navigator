from notifications.channel import NotificationChannel


class SmsChannel(NotificationChannel):
    def deliver(self, recipient: str, body: str) -> bool:
        return recipient.isdigit() and len(body) <= 160
