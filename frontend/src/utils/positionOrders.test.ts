import { describe, expect, it } from "vitest";
import type { PositionOrderWithPnL } from "@/api/types";
import {
  ACTIVE_DEFAULT_SORT,
  QTY_EPS,
  antSortOrder,
  partitionOrders,
  sortFromAnt,
  sortOrders,
} from "./positionOrders";

function order(
  partial: Partial<PositionOrderWithPnL> & { id: number }
): PositionOrderWithPnL {
  return {
    id: partial.id,
    position_id: partial.position_id ?? 1,
    source: partial.source ?? "manual",
    source_order_id: partial.source_order_id ?? null,
    open_qty: partial.open_qty ?? 1,
    remaining_qty: partial.remaining_qty ?? 1,
    entry_price: partial.entry_price ?? 50_000,
    leverage: partial.leverage ?? 10,
    margin: partial.margin ?? null,
    mmr: partial.mmr ?? null,
    liquidation_price: partial.liquidation_price ?? null,
    status: partial.status ?? "open",
    created_at: partial.created_at ?? "2026-01-01T00:00:00Z",
    updated_at: partial.updated_at ?? "2026-01-01T00:00:00Z",
    unrealized_pnl: partial.unrealized_pnl ?? 100,
    unrealized_pnl_pct: partial.unrealized_pnl_pct ?? 0.01,
    mark_price: partial.mark_price ?? 51_000,
    realized_pnl: partial.realized_pnl ?? 0,
    close_price: partial.close_price ?? null,
    unrealized_pnl_usdt: partial.unrealized_pnl_usdt,
    realized_pnl_usdt: partial.realized_pnl_usdt,
    pnl_asset: partial.pnl_asset,
  };
}

describe("partitionOrders", () => {
  it("splits active vs history by remaining_qty threshold", () => {
    const { active, history } = partitionOrders([
      order({ id: 1, remaining_qty: 0.5 }),
      order({ id: 2, remaining_qty: 0 }),
      order({ id: 3, remaining_qty: QTY_EPS / 2 }),
    ]);

    expect(active.map((o) => o.id)).toEqual([1]);
    expect(history.map((o) => o.id)).toEqual([2, 3]);
  });
});

describe("sortOrders", () => {
  it("sorts by entry_price ascending with id tie-break", () => {
    const sorted = sortOrders(
      [
        order({ id: 2, entry_price: 60_000 }),
        order({ id: 1, entry_price: 50_000 }),
        order({ id: 3, entry_price: 60_000 }),
      ],
      { field: "entry_price", order: "asc" }
    );
    expect(sorted.map((o) => o.id)).toEqual([1, 2, 3]);
  });

  it("prefers unrealized_pnl_usdt over unrealized_pnl when present", () => {
    const sorted = sortOrders(
      [
        order({ id: 1, unrealized_pnl: 999, unrealized_pnl_usdt: 10 }),
        order({ id: 2, unrealized_pnl: 1, unrealized_pnl_usdt: 50 }),
      ],
      { field: "unrealized_pnl", order: "desc" }
    );
    expect(sorted.map((o) => o.id)).toEqual([2, 1]);
  });

  it("uses default active sort without throwing", () => {
    const sorted = sortOrders(
      [
        order({ id: 1, created_at: "2026-01-02T00:00:00Z" }),
        order({ id: 2, created_at: "2026-01-01T00:00:00Z" }),
      ],
      ACTIVE_DEFAULT_SORT
    );
    expect(sorted.map((o) => o.id)).toEqual([2, 1]);
  });
});

describe("antSortOrder / sortFromAnt", () => {
  it("maps asc/desc to Ant Design table order", () => {
    expect(antSortOrder({ field: "created_at", order: "asc" })).toBe("ascend");
    expect(antSortOrder({ field: "created_at", order: "desc" })).toBe("descend");
  });

  it("round-trips Ant Design sorter state", () => {
    expect(sortFromAnt("entry_price", "descend")).toEqual({
      field: "entry_price",
      order: "desc",
    });
    expect(sortFromAnt("entry_price", null)).toEqual({
      field: "entry_price",
      order: "asc",
    });
  });
});
