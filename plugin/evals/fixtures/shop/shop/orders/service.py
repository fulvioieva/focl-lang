from datetime import datetime, timedelta

from shop import config
from shop.errors import NotFound, ShopError, error
from shop.notifications.mailer import send_order_email
from shop.orders.models import Order, OrderStatus
from shop.payments.gateway import PaymentGateway

CANCELLABLE = {OrderStatus.NEW, OrderStatus.PAID}


class OrderService:
    def __init__(self, repo, gateway: PaymentGateway):
        self.repo = repo
        self.gateway = gateway

    def get(self, user, order_id: int) -> Order:
        order = self.repo.find(order_id)
        # Same error for "missing" and "not yours": never leak other users' orders.
        if order is None or order.owner_id != user.id:
            raise error(NotFound, "ORDER_NOT_FOUND")
        return order

    def pay(self, user, order_id: int) -> Order:
        order = self.get(user, order_id)
        if order.status != OrderStatus.NEW:
            raise error(ShopError, "ORDER_ALREADY_PAID")
        if not order.lines:
            raise error(ShopError, "ORDER_EMPTY")
        order.payment_id = self.gateway.charge(order.total_cents, reference=f"order-{order.id}")
        order.status = OrderStatus.PAID
        self.repo.save(order)
        send_order_email(user.email, order, template="order_paid")
        return order

    def cancel(self, user, order_id: int) -> Order:
        order = self.get(user, order_id)
        if order.status not in CANCELLABLE:
            raise error(ShopError, "ORDER_NOT_CANCELLABLE")
        if order.status == OrderStatus.PAID:
            self.gateway.refund(order.payment_id, order.total_cents)
        order.status = OrderStatus.CANCELLED
        self.repo.save(order)
        send_order_email(user.email, order, template="order_cancelled")
        return order

    def refund(self, user, order_id: int) -> Order:
        order = self.get(user, order_id)
        if order.status != OrderStatus.DELIVERED:
            raise error(ShopError, "ORDER_NOT_DELIVERED")
        if datetime.utcnow() - order.delivered_at > timedelta(days=config.REFUND_WINDOW_DAYS):
            raise error(ShopError, "REFUND_WINDOW_EXPIRED")
        self.gateway.refund(order.payment_id, order.total_cents)
        order.status = OrderStatus.REFUNDED
        self.repo.save(order)
        send_order_email(user.email, order, template="order_refunded")
        return order
