import smtplib
from email.message import EmailMessage

from shop import config

TEMPLATES = {
    "order_paid": "Thanks! Order #{id} is paid.",
    "order_cancelled": "Order #{id} was cancelled.",
    "order_refunded": "Order #{id} was refunded.",
}


def send_order_email(to: str, order, template: str) -> None:
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = "orders@shop.example.com"
    msg["Subject"] = f"Your order #{order.id}"
    msg.set_content(TEMPLATES[template].format(id=order.id))
    with smtplib.SMTP(config.SMTP_HOST) as smtp:
        smtp.send_message(msg)
