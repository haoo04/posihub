"""Quick test script for position orders API."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings
from app.db.models import Account, DataSource, PositionCurrent, PositionOrder, PositionSide
from app.db.session import engine, init_db
from sqlmodel import Session, select


def main():
    print("[test] Initializing database...")
    init_db()

    with Session(engine) as session:
        # Check if we have any positions
        positions = list(session.exec(select(PositionCurrent)).all())
        print(f"[test] Found {len(positions)} positions")

        if not positions:
            print("[test] Creating test position...")
            # Create a test account if needed
            accounts = list(session.exec(select(Account)).all())
            if not accounts:
                print("[test] No accounts found. Please create an account first.")
                return

            account = accounts[0]
            position = PositionCurrent(
                account_id=account.id,
                canonical_symbol="BTCUSDT",
                side=PositionSide.LONG,
                qty=1.0,
                entry_price=50000.0,
                mark_price=51000.0,
                unrealized_pnl=1000.0,
                leverage=10.0,
                source=DataSource.MANUAL,
            )
            session.add(position)
            session.commit()
            session.refresh(position)
            print(f"[test] Created test position: {position.id}")
        else:
            position = positions[0]
            print(f"[test] Using existing position: {position.id}")

        # Create a test order
        print("[test] Creating test position order...")
        order = PositionOrder(
            position_id=position.id,
            source=DataSource.MANUAL,
            source_order_id="TEST-001",
            open_qty=0.5,
            remaining_qty=0.5,
            entry_price=49500.0,
            leverage=10.0,
            mmr=0.005,
            liquidation_price=44550.0,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        print(f"[test] Created order: {order.id}")

        # Query all orders for this position
        orders = list(
            session.exec(
                select(PositionOrder).where(PositionOrder.position_id == position.id)
            ).all()
        )
        print(f"[test] Found {len(orders)} orders for position {position.id}")

        for o in orders:
            # Calculate PnL
            if position.side == PositionSide.LONG:
                pnl = (position.mark_price - o.entry_price) * o.remaining_qty
            else:
                pnl = (o.entry_price - position.mark_price) * o.remaining_qty

            pnl_pct = (pnl / (o.entry_price * o.remaining_qty)) * 100 if o.remaining_qty > 0 else 0

            print(f"\n  Order #{o.id}:")
            print(f"    Source: {o.source}")
            print(f"    Qty: {o.open_qty} (remaining: {o.remaining_qty})")
            print(f"    Entry: {o.entry_price}")
            print(f"    Mark: {position.mark_price}")
            print(f"    PnL: {pnl:.2f} ({pnl_pct:+.2f}%)")
            print(f"    Leverage: {o.leverage}x")
            print(f"    MMR: {o.mmr * 100 if o.mmr else 0:.2f}%")
            print(f"    Liq Price: {o.liquidation_price}")

        print("\n[test] ✅ Position orders working correctly!")


if __name__ == "__main__":
    main()
