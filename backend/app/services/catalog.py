from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Cart, CartItem, CartStatus, Inventory, Product
from app.schemas import CartLineOut, CartOut, ProductOut
from app.services.errors import CartClosed, NotFound


def _product_rows(
    session: Session, product_ids: list[int] | None = None, category: str | None = None
):
    # One JOIN instead of N+1 lazy loads:
    #   SELECT products.*, inventory.quantity FROM products
    #   JOIN inventory ON inventory.product_id = products.id
    stmt = (
        select(Product, Inventory.quantity)
        .join(Inventory, Inventory.product_id == Product.id)
        .order_by(Product.id)
    )
    if product_ids is not None:
        stmt = stmt.where(Product.id.in_(product_ids))
    if category is not None:
        stmt = stmt.where(Product.category == category)
    return session.execute(stmt).all()


def to_product_out(product: Product, stock: int) -> ProductOut:
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        category=product.category,
        image_url=product.image_url,
        price_cents=product.price_cents,
        stock=stock,
    )


def list_products(session: Session, category: str | None = None) -> list[ProductOut]:
    return [to_product_out(p, q) for p, q in _product_rows(session, category=category)]


def get_product(session: Session, product_id: int) -> ProductOut:
    rows = _product_rows(session, [product_id])
    if not rows:
        raise NotFound(f"product {product_id} not found")
    product, stock = rows[0]
    return to_product_out(product, stock)


# ---------------------------------------------------------------------- carts


def create_cart(session: Session) -> CartOut:
    cart = Cart()
    session.add(cart)
    session.commit()
    return cart_out(session, cart)


def _open_cart(session: Session, cart_id: str) -> Cart:
    cart = session.get(Cart, cart_id)
    if cart is None:
        raise NotFound(f"cart {cart_id} not found")
    if cart.status is not CartStatus.OPEN:
        raise CartClosed("cart has already been checked out")
    return cart


def get_cart(session: Session, cart_id: str) -> CartOut:
    cart = session.get(Cart, cart_id)
    if cart is None:
        raise NotFound(f"cart {cart_id} not found")
    return cart_out(session, cart)


def set_cart_item(session: Session, cart_id: str, product_id: int, quantity: int) -> CartOut:
    """PUT semantics: set the quantity (idempotent). 0 removes the line.

    The cart does not reserve stock; stock is only claimed atomically at
    checkout. Reserving on add-to-cart would let abandoned carts lock inventory.
    """
    cart = _open_cart(session, cart_id)
    if session.get(Product, product_id) is None:
        raise NotFound(f"product {product_id} not found")
    item = session.get(CartItem, (cart_id, product_id))
    if quantity == 0:
        if item is not None:
            session.delete(item)
    elif item is None:
        session.add(CartItem(cart_id=cart_id, product_id=product_id, quantity=quantity))
    else:
        item.quantity = quantity
    session.commit()
    session.refresh(cart)
    return cart_out(session, cart)


def cart_out(session: Session, cart: Cart) -> CartOut:
    ids = [i.product_id for i in cart.items]
    stock = {p.id: q for p, q in _product_rows(session, ids)} if ids else {}
    lines = [
        CartLineOut(
            product=to_product_out(i.product, stock.get(i.product_id, 0)),
            quantity=i.quantity,
            line_total_cents=i.quantity * i.product.price_cents,
        )
        for i in cart.items
    ]
    return CartOut(
        id=cart.id,
        status=cart.status.value,
        items=lines,
        total_cents=sum(line.line_total_cents for line in lines),
    )
