import httpx

from shop import config
from shop.errors import ShopError, error


class PaymentGateway:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            base_url=config.PAYMENT_GATEWAY_URL,
            headers={"Authorization": f"Bearer {config.PAYMENT_API_KEY}"},
            timeout=10.0,
        )

    def charge(self, amount_cents: int, reference: str) -> str:
        resp = self.client.post("/charges", json={"amount": amount_cents,
                                                  "currency": "EUR", "reference": reference})
        if resp.status_code == 402:
            raise error(ShopError, "PAYMENT_DECLINED")
        resp.raise_for_status()
        return resp.json()["id"]

    def refund(self, payment_id: str, amount_cents: int) -> None:
        resp = self.client.post(f"/charges/{payment_id}/refunds", json={"amount": amount_cents})
        resp.raise_for_status()
