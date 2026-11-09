from fastapi import APIRouter, Depends

from shop.auth.tokens import current_user, require_role
from shop.orders.models import OrderStatus

router = APIRouter(prefix="/orders")


@router.get("")
def list_orders(status: OrderStatus | None = None, page: int = 1,
                user=Depends(current_user), repo=Depends()):
    return repo.list_for_owner(user.id, status=status, page=page)


@router.get("/{order_id}")
def get_order(order_id: int, user=Depends(current_user), svc=Depends()):
    return svc.get(user, order_id)


@router.post("/{order_id}/pay")
def pay_order(order_id: int, user=Depends(current_user), svc=Depends()):
    return svc.pay(user, order_id)


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, user=Depends(current_user), svc=Depends()):
    return svc.cancel(user, order_id)


@router.post("/{order_id}/refund")
def refund_order(order_id: int, user=Depends(current_user), svc=Depends()):
    require_role(user, "support")
    return svc.refund(user, order_id)
