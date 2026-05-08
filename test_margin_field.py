"""Quick test for margin field in position orders."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db.models import PositionOrder
from app.db.session import engine, init_db
from sqlmodel import Session, select


def main():
    print("[test] Testing margin field...")
    init_db()

    with Session(engine) as session:
        # Query all orders
        orders = list(session.exec(select(PositionOrder)).all())
        print(f"[test] Found {len(orders)} position orders")

        if orders:
            for order in orders:
                print(f"\nOrder #{order.id}:")
                print(f"  Qty: {order.open_qty}")
                print(f"  Entry: {order.entry_price}")
                print(f"  Leverage: {order.leverage}x")
                print(f"  Margin: {order.margin if order.margin is not None else 'Not set'}")
        else:
            print("[test] No orders found in database")

        print("\n[test] ✅ Margin field is accessible")


if __name__ == "__main__":
    main()
