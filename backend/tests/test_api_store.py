from sqlalchemy import select

from app.db.models import Inventory, Product

EMAIL = "ada@example.com"


def stock_of(db, sku):
    with db.session() as s:
        return s.scalar(select(Inventory.quantity).join(Product).where(Product.sku == sku))


def product_by_sku(client, sku):
    return next(p for p in client.get("/api/products").json() if p["sku"] == sku)


# ------------------------------------------------------------------ catalogue


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["database"] is True
    assert "x-request-id" in res.headers


def test_list_and_get_products(client):
    products = client.get("/api/products").json()
    assert len(products) == 24
    first = products[0]
    assert {"id", "sku", "name", "price_cents", "stock", "image_url"} <= first.keys()
    assert all(p["image_url"].startswith("https://images.unsplash.com/") for p in products)
    assert client.get(f"/api/products/{first['id']}").json() == first


def test_filter_products_by_category(client):
    kitchen = client.get("/api/products", params={"category": "Kitchen"}).json()
    assert kitchen and all(p["category"] == "Kitchen" for p in kitchen)


def test_missing_product_is_404_not_200(client):
    res = client.get("/api/products/9999")
    assert res.status_code == 404
    assert res.json()["code"] == "not_found"


def test_non_integer_path_param_is_422(client):
    assert client.get("/api/products/abc").status_code == 422


# ----------------------------------------------------------------------- cart


def test_cart_lifecycle(client):
    cart = client.post("/api/carts")
    assert cart.status_code == 201
    cid = cart.json()["id"]
    mug = product_by_sku(client, "MUG-001")

    res = client.put(f"/api/carts/{cid}/items/{mug['id']}", json={"quantity": 2})
    assert res.status_code == 200
    body = res.json()
    assert body["items"][0]["quantity"] == 2
    assert body["total_cents"] == 2 * mug["price_cents"]

    # PUT is idempotent: repeating it doesn't double the quantity.
    again = client.put(f"/api/carts/{cid}/items/{mug['id']}", json={"quantity": 2}).json()
    assert again["items"][0]["quantity"] == 2

    emptied = client.delete(f"/api/carts/{cid}/items/{mug['id']}").json()
    assert emptied["items"] == [] and emptied["total_cents"] == 0


def test_cart_errors(client):
    cid = client.post("/api/carts").json()["id"]
    assert client.get("/api/carts/nope").status_code == 404
    assert client.put(f"/api/carts/{cid}/items/9999", json={"quantity": 1}).status_code == 404
    assert client.put(f"/api/carts/{cid}/items/1", json={"quantity": -1}).status_code == 422
    assert client.put(f"/api/carts/{cid}/items/1", json={"quantity": 500}).status_code == 422


# --------------------------------------------------------------------- orders


def test_checkout_from_cart(client, db):
    cid = client.post("/api/carts").json()["id"]
    mug = product_by_sku(client, "MUG-001")
    client.put(f"/api/carts/{cid}/items/{mug['id']}", json={"quantity": 3})

    res = client.post("/api/orders", json={"customer_email": EMAIL, "cart_id": cid})
    assert res.status_code == 201
    order = res.json()
    assert order["status"] == "placed"
    assert order["total_cents"] == 3 * mug["price_cents"]
    assert order["items"][0]["unit_price_cents"] == mug["price_cents"]
    assert [e["status"] for e in order["events"]] == ["placed"]
    assert stock_of(db, "MUG-001") == mug["stock"] - 3

    # The cart is closed: checking out again or editing it is a conflict.
    again = client.post("/api/orders", json={"customer_email": EMAIL, "cart_id": cid})
    assert again.status_code == 409 and again.json()["code"] == "cart_closed"
    assert client.put(f"/api/carts/{cid}/items/1", json={"quantity": 1}).status_code == 409
    assert stock_of(db, "MUG-001") == mug["stock"] - 3

    fetched = client.get(f"/api/orders/{order['id']}").json()
    assert fetched["id"] == order["id"]
    assert client.get("/api/orders").json()[0]["id"] == order["id"]


def test_order_validation(client):
    def post(body):
        return client.post("/api/orders", json=body).status_code

    assert post({"customer_email": EMAIL}) == 422  # neither source
    assert post({"customer_email": EMAIL, "cart_id": "x", "items": []}) == 422  # both
    assert post({"customer_email": EMAIL, "items": []}) == 422
    assert (
        post({"customer_email": "not-an-email", "items": [{"product_id": 1, "quantity": 1}]}) == 422
    )
    assert post({"customer_email": EMAIL, "items": [{"product_id": 1, "quantity": 0}]}) == 422
    dup = [{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 2}]
    assert post({"customer_email": EMAIL, "items": dup}) == 422
    assert post({"customer_email": EMAIL, "items": [{"product_id": 999, "quantity": 1}]}) == 404

    cid = client.post("/api/carts").json()["id"]
    res = client.post("/api/orders", json={"customer_email": EMAIL, "cart_id": cid})
    assert res.status_code == 422 and res.json()["code"] == "empty_cart"


def test_out_of_stock_rolls_back_the_whole_order(client, db):
    mug = product_by_sku(client, "MUG-001")
    knife = product_by_sku(client, "KNF-004")
    res = client.post(
        "/api/orders",
        json={
            "customer_email": EMAIL,
            "items": [
                {"product_id": mug["id"], "quantity": 1},  # fine
                {"product_id": knife["id"], "quantity": knife["stock"] + 1},  # too many
            ],
        },
    )
    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "out_of_stock"
    assert body["available"] == knife["stock"] and body["requested"] == knife["stock"] + 1
    # Atomicity: the mug line must NOT have been deducted.
    assert stock_of(db, "MUG-001") == mug["stock"]
    assert stock_of(db, "KNF-004") == knife["stock"]
    assert client.get("/api/orders").json() == []


def test_idempotency_key_prevents_duplicate_orders(client, db):
    puzzle = product_by_sku(client, "MUG-001")
    body = {"customer_email": EMAIL, "items": [{"product_id": puzzle["id"], "quantity": 1}]}
    headers = {"Idempotency-Key": "checkout-abc-123"}

    first = client.post("/api/orders", json=body, headers=headers)
    second = client.post("/api/orders", json=body, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers["idempotent-replayed"] == "true"
    assert first.json()["id"] == second.json()["id"]
    assert stock_of(db, "MUG-001") == puzzle["stock"] - 1  # charged once
    assert len(client.get("/api/orders").json()) == 1

    other = dict(body, customer_email="eve@example.com")
    clash = client.post("/api/orders", json=other, headers=headers)
    assert clash.status_code == 422 and clash.json()["code"] == "idempotency_key_reused"


def test_order_stats(client):
    mug = product_by_sku(client, "MUG-001")
    client.post(
        "/api/orders",
        json={"customer_email": EMAIL, "items": [{"product_id": mug["id"], "quantity": 2}]},
    )
    stats = client.get("/api/metrics").json()["store"]
    assert stats["orders_by_status"]["placed"] == 1
    assert stats["revenue_cents"] == 2 * mug["price_cents"]
