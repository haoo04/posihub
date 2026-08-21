"""Repair legacy Bitget inverse PnL units.

Default mode is a read-only dry run.  Use ``python scripts/repair_coin_pnl_units.py
--apply`` after reviewing the report; the apply path creates a SQLite backup
before writing and records an idempotency marker in the database.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.db.session import engine, init_db, session_scope  # noqa: E402
from app.services.pnl_unit_repair import repair_coin_pnl_units  # noqa: E402


def _sqlite_path() -> Path | None:
    database = engine.url.database
    if (
        not database
        or engine.url.get_backend_name() != "sqlite"
        or database == ":memory:"
    ):
        return None
    return Path(database).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="write the conversion and record the migration marker",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="report candidates without changing rows (default)",
    )
    parser.add_argument(
        "--backup-path",
        type=Path,
        help="optional SQLite backup path (apply mode only)",
    )
    args = parser.parse_args()

    init_db()
    source = _sqlite_path()
    backup_path: Path | None = None
    if args.apply and source is not None:
        backup_path = (
            args.backup_path
            or source.with_name(
                f"{source.name}.bak-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            )
        ).resolve()
        shutil.copy2(source, backup_path)

    with session_scope() as session:
        report = repair_coin_pnl_units(session, dry_run=not args.apply)

    output = {
        "mode": "apply" if args.apply else "dry-run",
        "database": str(source) if source else get_settings().database_url,
        "backup": str(backup_path) if backup_path else None,
        "report": report.__dict__ if hasattr(report, "__dict__") else {
            name: getattr(report, name) for name in report.__dataclass_fields__
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
