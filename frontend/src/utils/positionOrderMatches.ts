import type { PositionOrderMatchRead } from "@/api/types";

/** Group position match rows by open leg, newest match first per order. */
export function groupMatchesByOpenOrderId(
  matches: PositionOrderMatchRead[]
): Map<number, PositionOrderMatchRead[]> {
  const map = new Map<number, PositionOrderMatchRead[]>();

  for (const match of matches) {
    const list = map.get(match.open_order_id) ?? [];
    list.push(match);
    map.set(match.open_order_id, list);
  }

  for (const list of map.values()) {
    list.sort((a, b) => {
      const dt =
        new Date(b.matched_at).getTime() - new Date(a.matched_at).getTime();
      return dt !== 0 ? dt : b.id - a.id;
    });
  }

  return map;
}

export function matchesForOrder(
  map: Map<number, PositionOrderMatchRead[]>,
  orderId: number
): PositionOrderMatchRead[] {
  return map.get(orderId) ?? [];
}

export function orderHasMatches(
  map: Map<number, PositionOrderMatchRead[]>,
  orderId: number
): boolean {
  return (map.get(orderId)?.length ?? 0) > 0;
}
