import os

DATABASE_URL = os.environ.get("SHOP_DATABASE_URL", "sqlite:///shop.db")
PAYMENT_GATEWAY_URL = os.environ.get("SHOP_PAYMENT_GATEWAY_URL", "https://pay.example.com/v2")
PAYMENT_API_KEY = os.environ["SHOP_PAYMENT_API_KEY"]
SMTP_HOST = os.environ.get("SHOP_SMTP_HOST", "localhost")
JWT_SECRET = os.environ["SHOP_JWT_SECRET"]
JWT_TTL_SECONDS = int(os.environ.get("SHOP_JWT_TTL_SECONDS", "3600"))
REFUND_WINDOW_DAYS = 14
