import { describe, expect, it } from "vitest";
import type { PositionOrderMatchRead } from "@/api/types";
import {
  groupMatchesByOpenOrderId,
  matchesForOrder,
  orderHasMatches,
} from "./positionOrderMatches";

function match(
  partial: Partial<PositionOrderMatchRead> & { id: number; open_order_id: number }
): PositionOrderMatchRead {
  return {
    id: partial.id,
    open_order_id: partial.open_order_id,
    close_order_id: partial.close_order_id ?? 100,
    matched_qty: partial.matched_qty ?? 0.5,
    open_price: partial.open_price ?? 50_000,
    close_price: partial.close_price ?? 51_000,
    realized_pnl: partial.realized_pnl ?? 500,
    matched_at: partial.matched_at ?? "2026-01-01T12:00:00Z",
  };
}

describe("groupMatchesByOpenOrderId", () => {
  it("groups by open_order_id and sorts newest match first", () => {
    const map = groupMatchesByOpenOrderId([
      match({ id: 1, open_order_id: 10, matched_at: "2026-01-01T10:00:00Z" }),
      match({ id: 2, open_order_id: 10, matched_at: "2026-01-02T10:00:00Z" }),
      match({ id: 3, open_order_id: 20, matched_at: "2026-01-01T08:00:00Z" }),
    ]);

    expect(map.get(10)?.map((m) => m.id)).toEqual([2, 1]);
    expect(map.get(20)?.map((m) => m.id)).toEqual([3]);
  });
});

describe("matchesForOrder / orderHasMatches", () => {
  it("returns empty list when order has no matches", () => {
    const map = groupMatchesByOpenOrderId([]);
    expect(matchesForOrder(map, 99)).toEqual([]);
    expect(orderHasMatches(map, 99)).toBe(false);
  });

  it("returns matches and detects presence", () => {
    const map = groupMatchesByOpenOrderId([
      match({ id: 1, open_order_id: 5 }),
    ]);
    expect(matchesForOrder(map, 5)).toHaveLength(1);
    expect(orderHasMatches(map, 5)).toBe(true);
  });
});
