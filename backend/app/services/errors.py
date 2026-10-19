class DomainError(Exception):
    """A business-rule failure that maps to a specific HTTP status."""

    status_code = 400
    code = "bad_request"

    def __init__(self, detail: str, **extra: object) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class OutOfStock(DomainError):
    status_code = 409
    code = "out_of_stock"


class CartClosed(DomainError):
    status_code = 409
    code = "cart_closed"


class IdempotencyMismatch(DomainError):
    # Same key, different body: the client has a bug. Stripe also rejects this.
    status_code = 422
    code = "idempotency_key_reused"


class EmptyCart(DomainError):
    status_code = 422
    code = "empty_cart"
