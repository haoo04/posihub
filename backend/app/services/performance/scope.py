"""Account scope resolution for performance queries."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from ...db.models import Account


@dataclass(slots=True)
class PerformanceScope:
    """Resolved set of accounts included in a performance query."""

    account_ids: list[int]
    exchange_id: int | None
    include_simulated: bool


def parse_account_ids(raw: str | None) -> list[int] | None:
    """Parse comma-separated account ids; ``None`` means no explicit filter."""

    if raw is None or not raw.strip():
        return None
    ids: list[int] = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        if not text.isdigit():
            raise ValueError(f"invalid account id: {text}")
        ids.append(int(text))
    return ids or None


def resolve_performance_scope(
    session: Session,
    *,
    account_ids: list[int] | None = None,
    exchange_id: int | None = None,
    include_simulated: bool = False,
) -> PerformanceScope:
    """Return enabled accounts matching the requested scope."""

    stmt = select(Account).where(Account.enabled == True)  # noqa: E712
    if not include_simulated:
        stmt = stmt.where(Account.is_simulated == False)  # noqa: E712
    if exchange_id is not None:
        stmt = stmt.where(Account.exchange_id == exchange_id)

    accounts = list(session.exec(stmt).all())
    if account_ids is not None:
        allowed = set(account_ids)
        accounts = [a for a in accounts if a.id in allowed]

    resolved = sorted(int(a.id) for a in accounts if a.id is not None)
    return PerformanceScope(
        account_ids=resolved,
        exchange_id=exchange_id,
        include_simulated=include_simulated,
    )
