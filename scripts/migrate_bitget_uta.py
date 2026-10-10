"""Explicit, read-only-by-default Bitget UTA schema and local data migration.

Run schema --apply before starting the updated backend on an existing SQLite
database. Probe/cutover require the Bitget account to be in Advanced UTA mode.
Stop the backend and scheduler before cutover --apply. No trading, transfers,
or exchange account-mode changes are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine, select

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.db.models import (
    Account, AccountBalanceCurrent, AccountSnapshotDaily, AccountType,
    DataMigration, DataSource, Exchange, ExchangeConnectionState,
    HistoryImportPreview, PositionCurrent, PositionSnapshotDaily,
)
from app.services.exchange.ccxt_client import CcxtExchangeClient
from app.services.snapshot_service import write_account_snapshot
from app.services.sync_service import sync_account

SCHEMA_KEY = "bitget-uta-schema-v1"
CUTOVER_PREFIX = "bitget-uta-cutover-v1:"
SCHEMA_COLUMNS = {
    "accounts": ("current_equity_usdt", "REAL"),
    "exchange_connection_states": ("details_json", "TEXT"),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _today():
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


def _backup(source: Path, backup_path: Path | None) -> dict:
    destination = (backup_path or source.with_name(
        f"{source.name}.bitget-uta-{_utcnow():%Y%m%dT%H%M%S%f}.sqlite3"
    )).resolve()
    if destination == source.resolve() or destination.exists():
        raise ValueError("Backup must be a new file distinct from the source database")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(str(destination)) as backup:
            original.backup(backup)
    with destination.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return {"backup": str(destination), "backup_sha256": digest}


def migrate_schema(source: Path, *, apply: bool = False, backup_path: Path | None = None) -> dict:
    source = source.resolve()
    report = {"command": "schema", "applied": False, "already_applied": False, "missing_columns": [], "blockers": []}
    with sqlite3.connect(source.as_uri() + ("?mode=rw" if apply else "?mode=ro"), uri=True) as connection:
        if apply:
            connection.execute("BEGIN IMMEDIATE")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, (name, expected) in SCHEMA_COLUMNS.items():
            if table not in tables:
                report["blockers"].append(f"Required table is missing: {table}")
                continue
            columns = {row[1]: row for row in connection.execute(f"PRAGMA table_info({table})")}
            column = columns.get(name)
            if column is None:
                report["missing_columns"].append(f"{table}.{name}")
            else:
                declared = column[2].upper()
                compatible = any(part in declared for part in (
                    ("REAL", "FLOA", "DOUB") if expected == "REAL" else ("TEXT", "CHAR", "CLOB")
                ))
                if not compatible or column[3]:
                    report["blockers"].append(f"Incompatible nullable column: {table}.{name}")
        marker = "data_migrations" in tables and connection.execute(
            "SELECT 1 FROM data_migrations WHERE key=?", (SCHEMA_KEY,)
        ).fetchone() is not None
        if marker and report["missing_columns"]:
            report["blockers"].append("Schema marker exists but required columns are missing")
        if report["blockers"]:
            connection.rollback()
            return report
        report["already_applied"] = bool(marker and not report["missing_columns"])
        if not apply or report["already_applied"]:
            connection.rollback()
            return report
        report.update(_backup(source, backup_path))
        for table, (name, declared) in SCHEMA_COLUMNS.items():
            if f"{table}.{name}" in report["missing_columns"]:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declared} NULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS data_migrations "
            "(key VARCHAR(128) PRIMARY KEY NOT NULL, details_json TEXT NOT NULL, applied_at DATETIME NOT NULL)"
        )
        connection.execute("INSERT INTO data_migrations (key, details_json, applied_at) VALUES (?, ?, ?)", (
            SCHEMA_KEY, json.dumps({"columns": report["missing_columns"]}), _utcnow().isoformat(sep=" "),
        ))
        connection.commit()
        report["applied"] = True
        report["columns_verified"] = all(
            name in {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for table, (name, _) in SCHEMA_COLUMNS.items()
        )
    return report


def _uta_client(account: Account) -> CcxtExchangeClient:
    return CcxtExchangeClient(
        "bitget", uta=True,
        api_key=decrypt_secret(account.api_key_enc),
        api_secret=decrypt_secret(account.api_secret_enc),
        passphrase=decrypt_secret(account.passphrase_enc),
    )


def _offline_checks(session: Session, target_id: int, source_ids: list[int]) -> tuple[list[Account], list[str]]:
    blockers = []
    if not source_ids or len(set(source_ids)) != len(source_ids) or target_id in source_ids:
        return [], ["Specify distinct source IDs excluding the target account"]
    ids = [target_id, *source_ids]
    accounts = [session.get(Account, account_id) for account_id in ids]
    for account_id, account in zip(ids, accounts):
        exchange = session.get(Exchange, account.exchange_id) if account else None
        if account is None or exchange is None or exchange.name != "bitget" or account.is_simulated:
            blockers.append(f"Account #{account_id} must be a real Bitget account")
        elif account.account_type not in {AccountType.SPOT, AccountType.USDT_PERP, AccountType.COIN_PERP, AccountType.BITGET_UTA}:
            blockers.append(f"Account #{account_id} has an unsupported account type")
        elif account_id != target_id and account.account_type == AccountType.BITGET_UTA:
            blockers.append(f"Source account #{account_id} must be a classic account")
    if blockers:
        return [], blockers
    active_preview = session.exec(select(HistoryImportPreview).where(
        HistoryImportPreview.account_id.in_(ids),
        HistoryImportPreview.committed_at == None,
        HistoryImportPreview.expires_at >= _utcnow(),
    )).first()
    if active_preview:
        blockers.append("An unexpired, uncommitted history preview exists")
    keys = set()
    for position in session.exec(select(PositionCurrent).where(PositionCurrent.account_id.in_(ids))).all():
        key = (position.canonical_symbol, position.side)
        if key in keys:
            blockers.append("Current position keys conflict; investigate before merging")
            break
        keys.add(key)
    for model in (AccountSnapshotDaily, PositionSnapshotDaily):
        if session.exec(select(model).where(model.account_id.in_(ids), model.snapshot_date >= _today())).first():
            blockers.append("A snapshot exists on or after the cutover date; use a later maintenance window")
            break
    return accounts, blockers


def probe_accounts(session: Session, target_id: int, source_ids: list[int]) -> tuple[dict, dict]:
    accounts, blockers = _offline_checks(session, target_id, source_ids)
    report = {"command": "probe", "applied": False, "target_account_id": target_id, "source_account_ids": source_ids, "blockers": blockers}
    if blockers:
        return report, {}
    report["target_current_type"] = accounts[0].account_type.value
    report["positions_to_move"] = len(session.exec(select(PositionCurrent.id).where(PositionCurrent.account_id.in_(source_ids))).all())
    report["balance_rows_to_clear"] = len(session.exec(select(AccountBalanceCurrent.id).where(AccountBalanceCurrent.account_id.in_([target_id, *source_ids]))).all())
    details = {}
    for index, account in enumerate(accounts):
        client = None
        try:
            client = _uta_client(account)
            if index == 0:
                details = client.fetch_account_details()
                blockers.extend(details.get("blockers", []))
                if not details.get("uid"):
                    blockers.append("Target UID is unavailable")
            else:
                info = client._bitget_read("privateUtaGetV3AccountInfo", {})
                uid = str(info.get("userId") or info.get("uid") or "")
                if not uid or uid != details.get("uid"):
                    blockers.append(f"Account #{account.id} belongs to a different or unknown UID")
                if info.get("permType") != "read-only" or "withdraw" in info.get("permissions", []):
                    blockers.append(f"Source account #{account.id} requires a read-only key without withdrawal permission")
        except Exception as exc:
            blockers.append(f"Read-only probe failed for account #{account.id} ({type(exc).__name__})")
        finally:
            if client is not None:
                client.close()
    if uid := details.get("uid"):
        report["uid_fingerprint"] = hashlib.sha256(uid.encode()).hexdigest()[:12]
        included = {target_id, *source_ids}
        for other in session.exec(select(Account).where(
            Account.enabled == True, Account.is_simulated == False,
            Account.exchange_id == accounts[0].exchange_id,
        )).all():
            if other.id in included:
                continue
            state = session.exec(select(ExchangeConnectionState).where(ExchangeConnectionState.account_id == other.id)).first()
            other_uid = json.loads(state.details_json or "{}").get("uid") if state else None
            if not other_uid or other_uid == uid:
                blockers.append(f"Enabled Bitget account #{other.id} has the same or an unknown UID; test or disable it first")
    report["capabilities"] = {
        key: details[key] for key in ("account_mode", "account_level", "hold_mode", "permission_type", "capabilities")
        if key in details
    }
    report["warnings"] = details.get("warnings", [])
    return report, details


def cutover_accounts(
    session: Session, source: Path, target_id: int, source_ids: list[int],
    *, apply: bool = False, backup_path: Path | None = None,
) -> dict:
    source_ids = sorted(source_ids)
    key = f"{CUTOVER_PREFIX}{target_id}"
    marker = session.get(DataMigration, key)
    if marker:
        stored = json.loads(marker.details_json)
        if stored["source_account_ids"] != source_ids:
            return {"command": "cutover", "applied": False, "blockers": ["This target was already migrated with different source IDs"]}
        target = session.get(Account, target_id)
        healthy = target is not None and target.current_equity_usdt is not None and target.last_sync_status == "ok"
        return {"command": "cutover", "applied": False, "already_applied": True,
                "blockers": [] if healthy else ["Cutover already applied; synchronize and validate the target before resuming the scheduler"],
                "target_account_id": target_id}
    if apply:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        session.expire_all()
    report, details = probe_accounts(session, target_id, source_ids)
    report["command"] = "cutover"
    if report["blockers"] or not apply:
        session.rollback()
        return report
    report.update(_backup(source.resolve(), backup_path))
    ids = [target_id, *source_ids]
    target = session.get(Account, target_id)
    try:
        positions = session.exec(select(PositionCurrent).where(PositionCurrent.account_id.in_(source_ids))).all()
        report["positions_moved"] = len(positions)
        for position in positions:
            position.account_id = target_id
            session.add(position)
        balances = session.exec(select(AccountBalanceCurrent).where(AccountBalanceCurrent.account_id.in_(ids))).all()
        report["balances_cleared"] = len(balances)
        for balance in balances:
            session.delete(balance)
        for account_id in ids:
            account = session.get(Account, account_id)
            account.enabled = account_id == target_id
            account.current_equity_usdt = None
            account.last_sync_at = None
            account.last_sync_status = None
            account.last_sync_error = None
            account.consecutive_failures = 0
            session.add(account)
        target.account_type = AccountType.BITGET_UTA
        state = session.exec(select(ExchangeConnectionState).where(ExchangeConnectionState.account_id == target_id)).first()
        if state is None:
            state = ExchangeConnectionState(account_id=target_id)
        state.status = "connected"
        state.last_test_at = _utcnow()
        state.message = "Read-only UTA cutover preflight passed"
        state.details_json = json.dumps(details)
        session.add(state)
        for source_state in session.exec(select(ExchangeConnectionState).where(ExchangeConnectionState.account_id.in_(source_ids))).all():
            source_state.status = "unknown"
            source_state.last_test_at = None
            source_state.latency_ms = None
            source_state.message = "Retired after UTA cutover"
            session.add(source_state)
        session.exec(delete(HistoryImportPreview).where(
            HistoryImportPreview.account_id.in_(ids), HistoryImportPreview.expires_at < _utcnow(),
        ))
        session.add(DataMigration(key=key, details_json=json.dumps({
            "target_account_id": target_id, "source_account_ids": source_ids,
            "positions_moved": report["positions_moved"], "balances_cleared": report["balances_cleared"],
            "uid_fingerprint": report["uid_fingerprint"], "cutover_date": _today().isoformat(),
        })))
        session.commit()
    except Exception as exc:
        session.rollback()
        report["blockers"].append(f"Cutover transaction rolled back ({type(exc).__name__})")
        return report
    report["applied"] = True
    try:
        outcome = sync_account(session, target)
        report["first_sync_succeeded"] = outcome.success
        if not outcome.success:
            target.enabled = False
            session.add(target)
            report["blockers"].append("Cutover committed, but first sync failed; target disabled. Restore the backup or repair and retry synchronization")
        session.commit()
        if outcome.success:
            with session.begin_nested() as validation:
                snapshot = write_account_snapshot(
                    session, account_id=target_id, snapshot_date=_today(), asset="USDT",
                    total_equity=target.current_equity_usdt, total_unrealized_pnl=0.0,
                    total_available=0.0, source=DataSource.API,
                )
                session.flush()
                report["snapshot_validated"] = snapshot.total_equity == target.current_equity_usdt
                validation.rollback()
    except Exception as exc:
        session.rollback()
        target = session.get(Account, target_id)
        target.enabled = False
        target.last_sync_status = "error"
        target.last_sync_error = "Post-cutover validation failed"
        session.add(target)
        session.commit()
        report["blockers"].append(f"Cutover committed; post-cutover validation failed ({type(exc).__name__}). Target disabled; restore backup or repair")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("schema", "probe", "cutover"):
        command = commands.add_parser(name)
        command.add_argument("--database-path", type=Path, help="SQLite file; defaults to configured DATABASE_URL")
        if name != "probe":
            mode = command.add_mutually_exclusive_group()
            mode.add_argument("--apply", action="store_true")
            mode.add_argument("--dry-run", action="store_true")
            command.add_argument("--backup-path", type=Path)
        if name != "schema":
            command.add_argument("--target-account-id", type=int, required=True)
            command.add_argument("--source-account-ids", nargs="+", type=int, required=True)
    args = parser.parse_args()
    engine = None
    try:
        if args.database_path:
            source = args.database_path.resolve()
        else:
            url = make_url(get_settings().database_url)
            if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
                raise ValueError("A SQLite file is required")
            source = Path(url.database).resolve()
        if not source.is_file():
            raise ValueError("The configured SQLite file does not exist")
        apply = getattr(args, "apply", False)
        if args.command == "schema":
            report = migrate_schema(source, apply=apply, backup_path=args.backup_path)
        else:
            engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(
                source.as_uri() + ("?mode=rw" if apply else "?mode=ro"), uri=True,
            ))
            with Session(engine) as session:
                if args.command == "probe":
                    report, _ = probe_accounts(session, args.target_account_id, args.source_account_ids)
                else:
                    report = cutover_accounts(session, source, args.target_account_id, args.source_account_ids, apply=apply, backup_path=args.backup_path)
        report["database"] = str(source)
    except Exception as exc:
        report = {"command": args.command, "applied": False, "blockers": [
            f"Migration stopped ({type(exc).__name__}); verify schema, database path and encrypted credentials"
        ]}
    finally:
        if engine:
            engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report.get("blockers") else 0


if __name__ == "__main__":
    raise SystemExit(main())
