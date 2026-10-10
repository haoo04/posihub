"""Exercise migration against synthetic SQLite files, never a live database."""

import hashlib
import json
import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from scripts import migrate_bitget_uta as migration
from app.db.models import (
    Account, AccountBalanceCurrent, AccountSnapshotDaily, AccountType,
    DataMigration, HistoryImportPreview, ManualEntry, PositionCloseExecution,
    PositionCurrent, PositionOrder, PositionOrderMatch, PositionSide,
)
from app.services.sync_service import SyncOutcome
from tests.test_bitget_uta import make_account, uta_client as _uta_client_fixture


@pytest.fixture(name="uta_client")
def migration_uta_client(monkeypatch):
    return _uta_client_fixture.__wrapped__(monkeypatch)


@pytest.fixture
def migration_db(tmp_path):
    path = tmp_path / "fixture.sqlite3"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        target = make_account(session, account_type=AccountType.SPOT)
        linear = make_account(session, account_type=AccountType.USDT_PERP)
        inverse = make_account(session, account_type=AccountType.COIN_PERP)
        spot_position = PositionCurrent(account_id=target.id, canonical_symbol="BTC-USDT-SPOT", side=PositionSide.LONG, qty=1)
        linear_position = PositionCurrent(account_id=linear.id, canonical_symbol="BTC-USDT-PERP", side=PositionSide.LONG, qty=1)
        inverse_position = PositionCurrent(account_id=inverse.id, canonical_symbol="ETH-USD-PERP", side=PositionSide.SHORT, qty=1)
        session.add_all([spot_position, linear_position, inverse_position])
        session.flush()
        order = PositionOrder(position_id=linear_position.id, source_order_id="fixture-open", open_qty=1, remaining_qty=0.5, entry_price=100)
        close = PositionCloseExecution(position_id=linear_position.id, source_order_id="fixture-close", close_qty=0.5, close_price=110)
        session.add_all([order, close])
        session.flush()
        session.add_all([
            PositionOrderMatch(open_order_id=order.id, close_order_id=close.id, matched_qty=0.5, open_price=100, close_price=110, realized_pnl=5),
            AccountBalanceCurrent(account_id=target.id, asset="USDT", equity=20),
            AccountBalanceCurrent(account_id=linear.id, asset="USDT", equity=30),
            AccountBalanceCurrent(account_id=inverse.id, asset="ETH", equity=1),
            AccountSnapshotDaily(account_id=linear.id, snapshot_date=migration._today() - timedelta(days=1), total_equity=30),
            ManualEntry(account_id=linear.id, entry_date=migration._today(), payload_json="{}"),
        ])
        session.commit()
        yield path, session, target.id, [linear.id, inverse.id], linear_position.id, order.id, close.id
    engine.dispose()


def test_schema_default_dry_run_backup_and_idempotence(tmp_path):
    source = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE exchange_connection_states (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO accounts (id) VALUES (1)")
    before = source.read_bytes()
    preview = migration.migrate_schema(source)
    assert len(preview["missing_columns"]) == 2 and not preview["applied"]
    assert source.read_bytes() == before
    report = migration.migrate_schema(source, apply=True)
    backup = Path(report["backup"])
    assert report["applied"] and report["columns_verified"]
    assert report["backup_sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
    with sqlite3.connect(backup) as connection:
        assert "current_equity_usdt" not in [row[1] for row in connection.execute("PRAGMA table_info(accounts)")]
        assert connection.execute("SELECT count(*) FROM accounts").fetchone()[0] == 1
    restored = tmp_path / "restored.sqlite3"
    shutil.copy2(backup, restored)
    assert hashlib.sha256(restored.read_bytes()).hexdigest() == report["backup_sha256"]
    after = source.read_bytes()
    assert migration.migrate_schema(source, apply=True)["already_applied"]
    assert source.read_bytes() == after


def test_schema_rejects_incompatible_existing_column_without_writes(tmp_path):
    source = tmp_path / "incompatible.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, current_equity_usdt INTEGER)")
        connection.execute("CREATE TABLE exchange_connection_states (id INTEGER PRIMARY KEY)")
    before = source.read_bytes()
    report = migration.migrate_schema(source, apply=True)
    assert report["blockers"] and not report["applied"]
    assert source.read_bytes() == before


def test_probe_and_cutover_dry_run_do_not_write_or_disclose_private_values(migration_db, uta_client, monkeypatch):
    source, session, target, sources, *_ = migration_db
    client, _ = uta_client
    monkeypatch.setattr(migration, "_uta_client", lambda _: client)
    before = source.read_bytes()
    report, _ = migration.probe_accounts(session, target, sources)
    assert report["blockers"] == []
    cutover = migration.cutover_accounts(session, source, target, sources)
    assert not cutover["applied"] and source.read_bytes() == before
    encoded = json.dumps(cutover)
    assert "1234567890" not in encoded and "15102" not in encoded and "synthetic-secret" not in encoded
    assert session.get(Account, target).account_type == AccountType.SPOT


@pytest.mark.parametrize("blocker", ["uid", "permissions", "basic", "debt", "usdc", "preview", "positions", "snapshot", "exchange"])
def test_cutover_blockers_leave_database_unchanged(migration_db, uta_client, monkeypatch, blocker):
    source, session, target, sources, position_id, *_ = migration_db
    client, api = uta_client
    monkeypatch.setattr(migration, "_uta_client", lambda _: client)
    if blocker == "uid":
        original = client._bitget_read
        client._bitget_read = lambda method, params: {"userId": "different"} if method == "privateUtaGetV3AccountInfo" else original(method, params)
        # Target settings UID mismatch also proves identity inconsistencies block.
    elif blocker == "permissions":
        api.info["permType"] = "read-and-write"
    elif blocker == "basic":
        api.settings["accountLevel"] = "basic"
    elif blocker == "debt":
        api.assets["assets"][0]["debt"] = "1"
    elif blocker == "usdc":
        api.positions["USDC-FUTURES"] = api.positions["USDT-FUTURES"]
    elif blocker == "preview":
        session.add(HistoryImportPreview(id="active", account_id=target, expires_at=migration._utcnow() + timedelta(minutes=10)))
    elif blocker == "positions":
        session.get(PositionCurrent, position_id).canonical_symbol = "BTC-USDT-SPOT"
    elif blocker == "snapshot":
        session.add(AccountSnapshotDaily(account_id=target, snapshot_date=migration._today(), total_equity=1))
    else:
        session.get(Account, target).is_simulated = True
    session.commit()
    before = source.read_bytes()
    report = migration.cutover_accounts(session, source, target, sources, apply=True)
    assert report["blockers"] and not report["applied"]
    assert source.read_bytes() == before
    assert session.get(Account, target).account_type == AccountType.SPOT


def successful_sync(session, account):
    account.current_equity_usdt = 150
    account.last_sync_status = "ok"
    session.add(account)
    session.add(AccountBalanceCurrent(account_id=account.id, asset="USDT", equity=100))
    return SyncOutcome(account.id, True, "ok")


def test_cutover_preserves_parent_ids_children_and_audits_and_is_idempotent(migration_db, uta_client, monkeypatch):
    source, session, target, sources, parent_id, order_id, close_id = migration_db
    client, _ = uta_client
    monkeypatch.setattr(migration, "_uta_client", lambda _: client)
    monkeypatch.setattr(migration, "sync_account", successful_sync)
    report = migration.cutover_accounts(session, source, target, sources, apply=True)
    assert report["applied"] and report["first_sync_succeeded"] and report["snapshot_validated"]
    assert report["positions_moved"] == 2 and report["balances_cleared"] == 3
    assert session.get(Account, target).account_type == AccountType.BITGET_UTA
    assert session.get(Account, target).enabled
    assert all(not session.get(Account, account_id).enabled for account_id in sources)
    assert session.get(PositionCurrent, parent_id).account_id == target
    assert session.get(PositionOrder, order_id).position_id == parent_id
    assert session.get(PositionCloseExecution, close_id).position_id == parent_id
    assert session.exec(select(PositionOrderMatch)).one().open_order_id == order_id
    assert session.exec(select(AccountSnapshotDaily)).one().account_id == sources[0]
    assert session.exec(select(ManualEntry)).one().account_id == sources[0]
    assert session.exec(select(AccountBalanceCurrent)).one().account_id == target
    assert session.get(DataMigration, f"{migration.CUTOVER_PREFIX}{target}")
    with sqlite3.connect(source) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before = source.read_bytes()
    monkeypatch.setattr(migration, "_uta_client", lambda _: pytest.fail("already-applied must not probe"))
    assert migration.cutover_accounts(session, source, target, list(reversed(sources)), apply=True)["already_applied"]
    assert source.read_bytes() == before
    with sqlite3.connect(report["backup"]) as connection:
        assert connection.execute("SELECT account_id FROM positions_current WHERE id=?", (parent_id,)).fetchone()[0] == sources[0]
        assert connection.execute("SELECT count(*) FROM account_balances_current").fetchone()[0] == 3


@pytest.mark.parametrize("exception", [False, True])
def test_first_sync_failure_reports_committed_cutover_and_disables_target(migration_db, uta_client, monkeypatch, exception):
    source, session, target, sources, *_ = migration_db
    client, _ = uta_client
    monkeypatch.setattr(migration, "_uta_client", lambda _: client)

    def failed_sync(*_):
        if exception:
            raise RuntimeError("private values must not leak")
        return SyncOutcome(target, False, "private values must not leak")

    monkeypatch.setattr(migration, "sync_account", failed_sync)
    report = migration.cutover_accounts(session, source, target, sources, apply=True)
    assert report["applied"] and report["blockers"]
    assert not session.get(Account, target).enabled
    assert session.get(DataMigration, f"{migration.CUTOVER_PREFIX}{target}")
    assert "private values" not in json.dumps(report)


def test_source_uid_mismatch_blocks_without_changing_accounts(migration_db, uta_client, monkeypatch):
    source, session, target, sources, *_ = migration_db
    client, _ = uta_client

    class OtherIdentity:
        def _bitget_read(self, *_):
            return {"userId": "9999999999", "permType": "read-only", "permissions": []}

        def close(self):
            pass

    monkeypatch.setattr(migration, "_uta_client", lambda account: client if account.id == target else OtherIdentity())
    before = source.read_bytes()
    result = migration.cutover_accounts(session, source, target, sources, apply=True)
    assert not result["applied"] and any("different" in blocker for blocker in result["blockers"])
    assert source.read_bytes() == before
