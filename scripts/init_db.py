"""Create database tables and print a summary.

Usage (from the project root):

    python -m scripts.init_db

The script is idempotent: re-running it on an existing DB does nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.db.session import engine, init_db  # noqa: E402


def main() -> None:
    setup_logging()
    settings = get_settings()
    print(f"[posihub] using database: {settings.database_url}")
    init_db()

    # quick sanity print of tables
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    print(f"[posihub] tables ready ({len(tables)}):")
    for name in tables:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
