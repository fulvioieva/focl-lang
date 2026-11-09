import time

import jwt

from shop import config
from shop.errors import Forbidden, error


def issue_token(user):
    now = int(time.time())
    payload = {"sub": str(user.id), "roles": list(user.roles), "iat": now,
               "exp": now + config.JWT_TTL_SECONDS}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def current_user(authorization: str, users):
    if not authorization.startswith("Bearer "):
        raise error(Forbidden, "AUTH_MISSING_TOKEN")
    try:
        payload = jwt.decode(authorization[7:], config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise error(Forbidden, "AUTH_TOKEN_EXPIRED")
    user = users.get(int(payload["sub"]))
    if user is None or not user.active:
        raise error(Forbidden, "AUTH_USER_DISABLED")
    return user


def require_role(user, role):
    if role not in user.roles:
        raise error(Forbidden, "AUTH_ROLE_REQUIRED")
