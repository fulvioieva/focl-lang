class ShopError(Exception):
    status = 400
    code = "SHOP_ERROR"


class NotFound(ShopError):
    status = 404


class Forbidden(ShopError):
    status = 403


def error(cls, code):
    exc = cls(code)
    exc.code = code
    return exc
