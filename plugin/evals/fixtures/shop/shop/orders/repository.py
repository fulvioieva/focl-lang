from shop.orders.models import Order, OrderStatus


class OrderRepository:
    def __init__(self, session):
        self.session = session

    def find(self, order_id: int) -> Order | None:
        return self.session.get(Order, order_id)

    def list_for_owner(self, owner_id: int, status: OrderStatus | None = None,
                       page: int = 1, size: int = 20) -> list[Order]:
        query = self.session.query(Order).filter(Order.owner_id == owner_id)
        if status is not None:
            query = query.filter(Order.status == status)
        return query.order_by(Order.id.desc()).offset((page - 1) * size).limit(size).all()

    def save(self, order: Order) -> Order:
        self.session.add(order)
        self.session.commit()
        return order
