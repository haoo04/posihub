import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PositionOrderWithPnL } from "@/api/types";
import { fmtContractValue, fmtQuantity } from "@/utils/format";
import { serializeCsv } from "@/utils/csv";
import { partitionOrders, quantityTolerance } from "@/utils/positionOrders";
import { PositionOrderModal } from "./PositionOrderModal";
import { PositionCloseFifoModal } from "./PositionCloseFifoModal";
import { PositionCloseSpecifiedModal } from "./PositionCloseSpecifiedModal";
import { PositionOrdersTable } from "./PositionOrdersTable";
import { PositionOrderMatchesPanel } from "./PositionOrderMatchesPanel";

const state = vi.hoisted(() => ({ mobile: false, orders: [] as PositionOrderWithPnL[] }));

vi.mock("antd", async (importOriginal) => {
  const antd = await importOriginal<typeof import("antd")>();
  return { ...antd, Modal: Object.assign(
    ({ children }: { children: ReactNode }) => createElement("div", null, children),
    { confirm: vi.fn() },
  ) };
});
vi.mock("@/api/hooks", () => ({
  queryKeys: {},
  usePositionOrders: () => ({ data: state.orders, isLoading: false }),
  usePositionMatches: () => ({ data: [], isLoading: false }),
  useCreatePositionOrder: () => ({ isPending: false }),
  useUpdatePositionOrder: () => ({ isPending: false }),
  useFifoClosePosition: () => ({ isPending: false }),
  useSpecifiedClosePosition: () => ({ isPending: false }),
  useDeletePositionOrder: () => ({ isPending: false }),
}));
vi.mock("@/hooks/useBreakpoint", () => ({ useBreakpoint: () => ({ isMobile: state.mobile }) }));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ invalidateQueries: vi.fn() }) }));

const inverseOrder: PositionOrderWithPnL = {
  id: 1, position_id: 1, source: "manual", source_order_id: null,
  quantity_mode: "quote_contract", quantity_unit: "USD",
  open_qty: 65, remaining_qty: 65, entry_price: 98, leverage: 1,
  margin: null, mmr: null, liquidation_price: null, status: "open",
  created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z",
  unrealized_pnl: 0.2918367347, unrealized_pnl_pct: 0.4489795918,
  mark_price: 98.44, realized_pnl: 0, pnl_asset: "SOL",
};
const props = {
  open: true, positionId: 1, quantityMode: "quote_contract" as const,
  quantityUnit: "USD", baseAsset: "SOL", onCancel: vi.fn(), onSuccess: vi.fn(),
};

beforeEach(() => { state.mobile = false; state.orders = [inverseOrder]; });

describe("Bybit inverse quantities", () => {
  it("labels new and existing orders as USD Filled Quantity", () => {
    for (const order of [undefined, inverseOrder]) {
      const html = renderToStaticMarkup(createElement(PositionOrderModal, { ...props, order }));
      expect(html).toContain("成交数量 (USD)");
      expect(html).toContain("请填写 Bybit 的 Filled Quantity，不要填写 SOL 成交额");
      expect(html).toContain('placeholder="65"');
    }
  });

  it("keeps existing labels for base and spot orders", () => {
    const base = { ...props, quantityMode: "base" as const, quantityUnit: "SOL" };
    expect(renderToStaticMarkup(createElement(PositionOrderModal, base))).toContain("开仓数量");
    expect(renderToStaticMarkup(createElement(PositionOrderModal, { ...base, isSpot: true }))).toContain("买入数量");
  });

  it("uses USD availability and allocation in both close forms", () => {
    const fifo = renderToStaticMarkup(createElement(PositionCloseFifoModal, props));
    expect(fifo).toContain("平仓成交数量 (USD)");
    expect(fifo).toContain("65 USD");
    const specified = renderToStaticMarkup(createElement(PositionCloseSpecifiedModal, props));
    expect(specified).toContain("剩余 (USD)");
    expect(specified).toContain("本次平仓 (USD)");
    expect(specified).toContain("65 USD");
  });

  it.each([false, true])("shows USD and the entry coin value on desktop/mobile (mobile=%s)", (mobile) => {
    state.mobile = mobile;
    const html = renderToStaticMarkup(createElement(PositionOrdersTable, {
      ...props, isCoinMargined: true, pnlAsset: "SOL",
    }));
    expect(html).toContain("65 USD");
    expect(html).toContain("0.66326531 SOL");
  });

  it("labels historical orders and matched quantities in USD", () => {
    state.orders = [{ ...inverseOrder, remaining_qty: 0, status: "closed" }];
    const { history } = partitionOrders(state.orders);
    expect(fmtQuantity(history[0].open_qty, history[0].quantity_unit)).toBe("65 USD");
    const matches = renderToStaticMarkup(createElement(PositionOrderMatchesPanel, { matches: [{
      id: 1, open_order_id: 1, close_order_id: 1, matched_qty: 65,
      open_price: 98, close_price: 98.44, realized_pnl: 0.2918367347,
      matched_at: "2026-10-10T01:00:00Z", quantity_mode: "quote_contract", quantity_unit: "USD",
    }] }));
    expect(matches).toContain("65 USD");
  });

  it("previews entry and close coin values without changing the USD quantity", () => {
    expect(fmtContractValue(65, 98, "SOL")).toBe("0.66326531 SOL");
    expect(fmtContractValue(65, 98.44, "SOL")).toBe("0.66030069 SOL");
    expect(fmtContractValue(65, 0, "SOL")).toBeNull();
    expect(fmtQuantity(65.25, "USD")).toBe("65.25 USD");
    expect(fmtQuantity(null, "USD")).toBe("—");
  });

  it("keeps exported quantities numeric with a separate unit column", () => {
    const csv = serializeCsv([
      { header: "数量", value: (row) => row.open_qty },
      { header: "数量单位", value: (row) => row.quantity_unit },
    ], [inverseOrder]);
    expect(csv).toContain("数量,数量单位\n65,USD");
    expect(csv).not.toContain("65 USD");
  });

  it("applies legacy tolerance in USD while keeping base-account tolerance", () => {
    expect(quantityTolerance(inverseOrder)).toBeCloseTo(0.00000098, 12);
    expect(quantityTolerance({ quantity_mode: "base", entry_price: 98 })).toBe(1e-9);
    const { active } = partitionOrders([{ ...inverseOrder, remaining_qty: 1e-10 }]);
    expect(active).toHaveLength(1);
  });
});
