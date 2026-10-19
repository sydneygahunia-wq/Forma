"""Race conditions, tested with real threads and separate DB sessions.

These call the service layer directly (one session per thread, like one
request per worker) so many transactions genuinely overlap.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.db.models import Inventory, Order, Product
from app.schemas import OrderCreate, OrderLineIn
from app.services.errors import OutOfStock
from app.services.orders import place_order


def _product(db, sku):
    with db.session() as s:
        return s.scalar(select(Product).where(Product.sku == sku))


def _stock(db, product_id):
    with db.session() as s:
        return s.scalar(select(Inventory.quantity).where(Inventory.product_id == product_id))


def _race(n, fn):
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()  # release every thread at the same moment
        return fn(i)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))


def test_many_buyers_for_the_last_unit(migrated_db):
    db = migrated_db
    puzzle = _product(db, "PZL-024")  # seeded with exactly 1 unit
    assert _stock(db, puzzle.id) == 1

    def buy(i):
        body = OrderCreate(
            customer_email=f"buyer{i}@example.com",
            items=[OrderLineIn(product_id=puzzle.id, quantity=1)],
        )
        with db.session() as s:
            try:
                place_order(s, body)
                return "ok"
            except OutOfStock:
                return "sold_out"

    results = _race(12, buy)
    assert results.count("ok") == 1, results
    assert results.count("sold_out") == 11
    assert _stock(db, puzzle.id) == 0  # never negative
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Order)) == 1


def test_concurrent_partial_stock_never_oversells(migrated_db):
    db = migrated_db
    knife = _product(db, "KNF-004")
    start = _stock(db, knife.id)  # 8 units, 20 buyers wanting 1 each

    def buy(i):
        body = OrderCreate(
            customer_email=f"b{i}@example.com",
            items=[OrderLineIn(product_id=knife.id, quantity=1)],
        )
        with db.session() as s:
            try:
                place_order(s, body)
                return 1
            except OutOfStock:
                return 0

    sold = sum(_race(20, buy))
    assert sold == start
    assert _stock(db, knife.id) == 0


def test_duplicate_requests_racing_with_the_same_idempotency_key(migrated_db):
    db = migrated_db
    mug = _product(db, "MUG-001")
    start = _stock(db, mug.id)
    body = OrderCreate(
        customer_email="dup@example.com", items=[OrderLineIn(product_id=mug.id, quantity=2)]
    )

    def submit(_i):
        with db.session() as s:
            res = place_order(s, body, idempotency_key="same-key")
            return res.order.id, res.created

    results = _race(8, submit)
    order_ids = {oid for oid, _ in results}
    assert len(order_ids) == 1, "every retry must resolve to the same order"
    assert sum(created for _, created in results) == 1
    assert _stock(db, mug.id) == start - 2  # deducted exactly once
