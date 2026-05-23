import type { PositionOrderWithPnL } from "@/api/types";

export const QTY_EPS = 1e-9;

export type OrderSortField =
  | "created_at"
  | "updated_at"
  | "entry_price"
  | "open_qty"
  | "remaining_qty"
  | "unrealized_pnl"
  | "realized_pnl"
  | "close_price";

export type SortOrder = "asc" | "desc";

export interface OrderSortState {
  field: OrderSortField;
  order: SortOrder;
}

export const ACTIVE_DEFAULT_SORT: OrderSortState = {
  field: "created_at",
  order: "asc",
};

export const HISTORY_DEFAULT_SORT: OrderSortState = {
  field: "updated_at",
  order: "desc",
};

export function partitionOrders(orders: PositionOrderWithPnL[]) {
  const active: PositionOrderWithPnL[] = [];
  const history: PositionOrderWithPnL[] = [];

  for (const order of orders) {
    if (order.remaining_qty > QTY_EPS) {
      active.push(order);
    } else {
      history.push(order);
    }
  }

  return { active, history };
}

function compareField(
  a: PositionOrderWithPnL,
  b: PositionOrderWithPnL,
  field: OrderSortField
): number {
  switch (field) {
    case "created_at":
    case "updated_at":
      return (
        new Date(a[field]).getTime() - new Date(b[field]).getTime()
      );
    case "entry_price":
    case "open_qty":
    case "remaining_qty":
      return a[field] - b[field];
    case "unrealized_pnl":
      return (
        (a.unrealized_pnl_usdt ?? a.unrealized_pnl) -
        (b.unrealized_pnl_usdt ?? b.unrealized_pnl)
      );
    case "realized_pnl":
      return (
        (a.realized_pnl_usdt ?? a.realized_pnl) -
        (b.realized_pnl_usdt ?? b.realized_pnl)
      );
    case "close_price":
      return (a.close_price ?? 0) - (b.close_price ?? 0);
    default:
      return 0;
  }
}

export function sortOrders(
  orders: PositionOrderWithPnL[],
  sort: OrderSortState
): PositionOrderWithPnL[] {
  const mul = sort.order === "asc" ? 1 : -1;
  return [...orders].sort((a, b) => {
    const cmp = compareField(a, b, sort.field);
    if (cmp !== 0) return cmp * mul;
    return (a.id - b.id) * mul;
  });
}

export function antSortOrder(
  sort: OrderSortState
): "ascend" | "descend" | null {
  return sort.order === "asc" ? "ascend" : "descend";
}

export function sortFromAnt(
  field: OrderSortField,
  order: "ascend" | "descend" | null | undefined
): OrderSortState {
  return {
    field,
    order: order === "descend" ? "desc" : "asc",
  };
}
