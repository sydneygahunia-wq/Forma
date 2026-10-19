"""Idempotent demo catalogue. Run directly with ``python -m app.db.seed``."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Inventory, Product

# Product photos from Unsplash (free to use under the Unsplash License).
UNSPLASH = "https://images.unsplash.com/photo-{}?w=800&h=800&fit=crop&auto=format&q=75"
IMAGE_IDS: dict[str, str] = {
    "MUG-001": "1616241673111-508b4662c707",
    "BTL-002": "1602143407151-7111542de6e8",
    "PAN-003": "1637739699971-7d4d5194e75c",
    "KNF-004": "1614362705324-8da11fd16754",
    "TEA-005": "1766232578337-ff7bdb6d1f8b",
    "NTB-006": "1787640619073-3dcb10c316c4",
    "PEN-007": "1583485088034-697b5bc54ccd",
    "LMP-008": "1519219788971-8d9797e0928e",
    "HDP-009": "1505740420928-5e560c06d30e",
    "KBD-010": "1777259113729-9bda92fb8ce8",
    "MSE-011": "1527864550417-7fd91fc51a46",
    "CBL-012": "1595756630452-736bc8ef3693",
    "BAT-013": "1760708825913-65a50b3dc39b",
    "SPK-014": "1608043152269-423dbba4e7e1",
    "PLT-015": "1520302630591-fd1c66edc19d",
    "CDL-016": "1757688525739-8d1e13daf44f",
    "BLK-017": "1734553529922-bc020a21643b",
    "CLK-018": "1563861826100-9cb868fdbe1c",
    "BKP-019": "1553062407-98eeb64c6a62",
    "CAP-020": "1588850561407-ed78c282e89b",
    "SNG-021": "1511499767150-a48a237f0083",
    "UMB-022": "1499678450342-29ebee16d1ab",
    "BAL-023": "1575361204480-aadea25e6e68",
    "PZL-024": "1776057441344-38e0587ad1e6",
}

# sku, name, category, price_cents, stock
CATALOGUE: list[tuple[str, str, str, int, int]] = [
    ("MUG-001", "Ceramic Mug", "Kitchen", 1299, 40),
    ("BTL-002", "Steel Water Bottle", "Kitchen", 2499, 30),
    ("PAN-003", "Cast Iron Pan", "Kitchen", 4599, 12),
    ("KNF-004", "Chef's Knife", "Kitchen", 6999, 8),
    ("TEA-005", "Loose Leaf Tea", "Kitchen", 1499, 50),
    ("NTB-006", "Dot Grid Notebook", "Office", 1899, 60),
    ("PEN-007", "Gel Pen 5-Pack", "Office", 899, 80),
    ("LMP-008", "Desk Lamp", "Office", 3999, 15),
    ("HDP-009", "Headphones", "Electronics", 12999, 10),
    ("KBD-010", "Mechanical Keyboard", "Electronics", 10999, 9),
    ("MSE-011", "Wireless Mouse", "Electronics", 3499, 25),
    ("CBL-012", "USB-C Cable", "Electronics", 1299, 100),
    ("BAT-013", "Power Bank", "Electronics", 4499, 20),
    ("SPK-014", "Bluetooth Speaker", "Electronics", 5999, 14),
    ("PLT-015", "Potted Succulent", "Home", 1599, 30),
    ("CDL-016", "Soy Candle", "Home", 2199, 35),
    ("BLK-017", "Wool Blanket", "Home", 7999, 6),
    ("CLK-018", "Wall Clock", "Home", 2999, 11),
    ("BKP-019", "Daypack", "Outdoor", 6499, 13),
    ("CAP-020", "Baseball Cap", "Outdoor", 2499, 40),
    ("SNG-021", "Sunglasses", "Outdoor", 3999, 18),
    ("UMB-022", "Umbrella", "Outdoor", 1999, 22),
    ("BAL-023", "Soccer Ball", "Outdoor", 2999, 16),
    ("PZL-024", "1000-Piece Puzzle", "Toys", 2499, 1),  # last unit: demo the race
]


def image_url(sku: str) -> str | None:
    photo = IMAGE_IDS.get(sku)
    return UNSPLASH.format(photo) if photo else None


def seed(session: Session) -> int:
    """Insert any catalogue products that don't exist yet, and backfill images
    on existing rows. Returns rows inserted."""
    existing = {p.sku: p for p in session.scalars(select(Product))}
    added = 0
    for sku, name, category, price, stock in CATALOGUE:
        if sku in existing:
            if existing[sku].image_url is None:
                existing[sku].image_url = image_url(sku)
            continue
        product = Product(
            sku=sku,
            name=name,
            category=category,
            image_url=image_url(sku),
            price_cents=price,
            description=f"{name} from the Forma demo catalogue.",
        )
        product.inventory = Inventory(quantity=stock)
        session.add(product)
        added += 1
    session.commit()
    return added


if __name__ == "__main__":
    from app.config import get_settings
    from app.db.session import Database

    db = Database(get_settings().database_url)
    with db.session() as s:
        print(f"seeded {seed(s)} products")
