import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { http } from "./client";
import type {
  Account,
  AccountCreate,
  AccountSnapshot,
  AccountSyncStatus,
  Exchange,
  FifoCloseResponse,
  Health,
  HistoryImportCommitResponse,
  HistoryImportPreviewRequest,
  HistoryImportPreviewResponse,
  ManualSnapshotCreate,
  ManualSnapshotResult,
  Overview,
  PnlSeries,
  PerformanceQueryParams,
  PerformanceSummary,
  EquityPerformanceSeries,
  PerformanceBreakdown,
  BreakdownDimension,
  RealizedPnlSeries,
  TradesPage,
  TradesQueryParams,
  PositionCloseExecutionRead,
  PositionCloseRequest,
  PositionMerged,
  PositionOrderCreate,
  PositionOrderMatchRead,
  PositionOrderUpdate,
  PositionOrderWithPnL,
  PositionSnapshot,
  PositionSplit,
  PositionMarket,
  SpecifiedCloseRequest,
  SymbolMapping,
} from "./types";

export const queryKeys = {
  health: ["health"] as const,
  overview: ["overview"] as const,
  exchanges: ["exchanges"] as const,
  accounts: ["accounts"] as const,
  positions: (view: "split" | "merged", market: PositionMarket = "derivatives") =>
    ["positions", view, market] as const,
  positionOrders: (positionId?: number) =>
    positionId ? ["position-orders", positionId] : ["position-orders"] as const,
  positionMatches: (positionId: number) =>
    ["position-matches", positionId] as const,
  positionCloseExecutions: (positionId: number) =>
    ["position-close-executions", positionId] as const,
  pnl: (range: string, asset: string) => ["pnl", range, asset] as const,
  performanceSummary: (params: PerformanceQueryParams) =>
    ["performance", "summary", params] as const,
  performanceEquity: (params: PerformanceQueryParams) =>
    ["performance", "equity", params] as const,
  performanceBreakdown: (
    dimension: BreakdownDimension,
    params: PerformanceQueryParams
  ) => ["performance", "breakdown", dimension, params] as const,
  performanceRealized: (params: PerformanceQueryParams) =>
    ["performance", "realized", params] as const,
  performanceTrades: (params: TradesQueryParams) =>
    ["performance", "trades", params] as const,
  accountSnapshots: (params: Record<string, unknown> = {}) =>
    ["snapshots", "accounts", params] as const,
  positionSnapshots: (params: Record<string, unknown> = {}) =>
    ["snapshots", "positions", params] as const,
  symbols: ["symbols"] as const,
};

export function useHealth(
  options?: Omit<UseQueryOptions<Health>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async () => (await http.get<Health>("/health")).data,
    staleTime: 60_000,
    ...options,
  });
}

export function useOverview(
  options?: Omit<UseQueryOptions<Overview>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: queryKeys.overview,
    queryFn: async () => (await http.get<Overview>("/api/v1/overview")).data,
    ...options,
  });
}

export function useExchanges() {
  return useQuery({
    queryKey: queryKeys.exchanges,
    queryFn: async () => (await http.get<Exchange[]>("/api/v1/exchanges")).data,
  });
}

export function useCreateExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; enabled?: boolean }) =>
      (await http.post<Exchange>("/api/v1/exchanges", payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.exchanges });
    },
  });
}

export function useAccounts() {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: async () => (await http.get<Account[]>("/api/v1/accounts")).data,
  });
}

export function useCreateAccount(
  options?: UseMutationOptions<Account, Error, AccountCreate>
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload) =>
      (await http.post<Account>("/api/v1/accounts", payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.accounts });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
    },
    ...options,
  });
}

export function useUpdateAccount(
  options?: UseMutationOptions<
    Account,
    Error,
    { id: number; patch: Partial<AccountCreate> }
  >
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, patch }) =>
      (await http.patch<Account>(`/api/v1/accounts/${id}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.accounts }),
    ...options,
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await http.delete(`/api/v1/accounts/${id}`);
      return id;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.accounts });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
    },
  });
}

export function useSyncAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      (await http.post<AccountSyncStatus>(`/api/v1/accounts/${id}/sync`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.accounts });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
      qc.invalidateQueries({ queryKey: ["positions"] });
    },
  });
}

export function useHistoryImportPreview() {
  return useMutation({
    mutationFn: async ({
      accountId,
      payload,
    }: {
      accountId: number;
      payload: HistoryImportPreviewRequest;
    }) =>
      (
        await http.post<HistoryImportPreviewResponse>(
          `/api/v1/accounts/${accountId}/history-import/preview`,
          payload
        )
      ).data,
  });
}

export function useHistoryImportCommit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      accountId,
      previewId,
    }: {
      accountId: number;
      previewId: string;
    }) =>
      (
        await http.post<HistoryImportCommitResponse>(
          `/api/v1/accounts/${accountId}/history-import/commit`,
          { preview_id: previewId }
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["position-orders"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
    },
  });
}

export function usePositions<V extends "split" | "merged">(
  view: V,
  market: PositionMarket = "derivatives"
) {
  return useQuery({
    queryKey: queryKeys.positions(view, market),
    queryFn: async () => {
      type Result = V extends "split" ? PositionSplit[] : PositionMerged[];
      const resp = await http.get<Result>(
        `/api/v1/positions?view=${view}&market=${market}`
      );
      return resp.data;
    },
    placeholderData: (previous) => previous,
  });
}

export function usePnl(range: string, asset = "USDT") {
  return useQuery({
    queryKey: queryKeys.pnl(range, asset),
    queryFn: async () =>
      (
        await http.get<PnlSeries>(
          `/api/v1/pnl?range=${range}&asset=${asset}`
        )
      ).data,
  });
}

function performanceSearchParams(params: PerformanceQueryParams): string {
  const qs = new URLSearchParams({ range: params.range });
  if (params.asset) qs.set("asset", params.asset);
  if (params.account_ids?.length) {
    qs.set("account_ids", params.account_ids.join(","));
  }
  if (params.include_simulated) {
    qs.set("include_simulated", "true");
  }
  return qs.toString();
}

export function usePerformanceSummary(params: PerformanceQueryParams) {
  return useQuery({
    queryKey: queryKeys.performanceSummary(params),
    queryFn: async () =>
      (
        await http.get<PerformanceSummary>(
          `/api/v1/performance/summary?${performanceSearchParams(params)}`
        )
      ).data,
  });
}

export function usePerformanceEquity(params: PerformanceQueryParams) {
  return useQuery({
    queryKey: queryKeys.performanceEquity(params),
    queryFn: async () =>
      (
        await http.get<EquityPerformanceSeries>(
          `/api/v1/performance/equity?${performanceSearchParams(params)}`
        )
      ).data,
  });
}

export function usePerformanceBreakdown(
  dimension: BreakdownDimension,
  params: PerformanceQueryParams
) {
  return useQuery({
    queryKey: queryKeys.performanceBreakdown(dimension, params),
    queryFn: async () => {
      const qs = performanceSearchParams(params);
      return (
        await http.get<PerformanceBreakdown>(
          `/api/v1/performance/breakdown?dimension=${dimension}&${qs}`
        )
      ).data;
    },
    placeholderData: (previous) => previous,
  });
}

export function usePerformanceRealized(params: PerformanceQueryParams) {
  return useQuery({
    queryKey: queryKeys.performanceRealized(params),
    queryFn: async () =>
      (
        await http.get<RealizedPnlSeries>(
          `/api/v1/performance/realized?${performanceSearchParams(params)}`
        )
      ).data,
  });
}

function tradesSearchParams(params: TradesQueryParams): string {
  const qs = new URLSearchParams(performanceSearchParams(params));
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.sort_field) qs.set("sort_field", params.sort_field);
  if (params.sort_desc !== undefined) {
    qs.set("sort_desc", String(params.sort_desc));
  }
  return qs.toString();
}

export function usePerformanceTrades(params: TradesQueryParams) {
  return useQuery({
    queryKey: queryKeys.performanceTrades(params),
    queryFn: async () =>
      (
        await http.get<TradesPage>(
          `/api/v1/performance/trades?${tradesSearchParams(params)}`
        )
      ).data,
    placeholderData: (previous) => previous,
  });
}

export function useAccountSnapshots(params: {
  start?: string;
  end?: string;
  account_id?: number;
} = {}) {
  return useQuery({
    queryKey: queryKeys.accountSnapshots(params),
    queryFn: async () =>
      (
        await http.get<AccountSnapshot[]>(
          "/api/v1/snapshots/daily/accounts",
          { params }
        )
      ).data,
  });
}

export function usePositionSnapshots(params: {
  start?: string;
  end?: string;
  account_id?: number;
  canonical_symbol?: string;
} = {}) {
  return useQuery({
    queryKey: queryKeys.positionSnapshots(params),
    queryFn: async () =>
      (
        await http.get<PositionSnapshot[]>(
          "/api/v1/snapshots/daily/positions",
          { params }
        )
      ).data,
  });
}

export function useRunDailySnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      (await http.post("/api/v1/snapshots/daily/run")).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["snapshots"] });
      qc.invalidateQueries({ queryKey: ["pnl"] });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
    },
  });
}

export function useCreateManualSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ManualSnapshotCreate) =>
      (
        await http.post<ManualSnapshotResult>(
          "/api/v1/manual/snapshot",
          payload
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["snapshots"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
      qc.invalidateQueries({ queryKey: ["pnl"] });
    },
  });
}

export function useSymbols() {
  return useQuery({
    queryKey: queryKeys.symbols,
    queryFn: async () =>
      (await http.get<SymbolMapping[]>("/api/v1/symbols")).data,
  });
}

export interface SymbolMappingPatch {
  canonical_symbol?: string;
  base_asset?: string;
  quote_asset?: string;
  instrument_type?: SymbolMapping["instrument_type"];
  contract_size?: number;
  is_active?: boolean;
}

export function useUpdateSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      patch,
    }: {
      id: number;
      patch: SymbolMappingPatch;
    }) =>
      (await http.patch<SymbolMapping>(`/api/v1/symbols/${id}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.symbols }),
  });
}

export function useDeleteSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await http.delete(`/api/v1/symbols/${id}`);
      return id;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.symbols }),
  });
}

export function usePositionOrders(positionId: number) {
  return useQuery({
    queryKey: queryKeys.positionOrders(positionId),
    queryFn: async () =>
      (
        await http.get<PositionOrderWithPnL[]>(
          `/api/v1/position-orders/by-position/${positionId}`
        )
      ).data,
    enabled: !!positionId,
  });
}

export function useCreatePositionOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PositionOrderCreate) =>
      (await http.post("/api/v1/position-orders", payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["position-orders"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
    },
  });
}

export function useUpdatePositionOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      update,
    }: {
      id: number;
      update: PositionOrderUpdate;
    }) => (await http.patch(`/api/v1/position-orders/${id}`, update)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["position-orders"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
    },
  });
}

export function useDeletePositionOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await http.delete(`/api/v1/position-orders/${id}`);
      return id;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["position-orders"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
    },
  });
}

export function useFifoClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      positionId,
      payload,
    }: {
      positionId: number;
      payload: PositionCloseRequest;
    }) =>
      (
        await http.post<FifoCloseResponse>(
          `/api/v1/positions/${positionId}/close-fifo`,
          payload
        )
      ).data,
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["position-orders"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({
        queryKey: queryKeys.positionMatches(variables.positionId),
      });
      qc.invalidateQueries({
        queryKey: queryKeys.positionCloseExecutions(variables.positionId),
      });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
    },
  });
}

export function useSpecifiedClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      positionId,
      payload,
    }: {
      positionId: number;
      payload: SpecifiedCloseRequest;
    }) =>
      (
        await http.post<FifoCloseResponse>(
          `/api/v1/positions/${positionId}/close-specified`,
          payload
        )
      ).data,
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["position-orders"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({
        queryKey: queryKeys.positionMatches(variables.positionId),
      });
      qc.invalidateQueries({
        queryKey: queryKeys.positionCloseExecutions(variables.positionId),
      });
      qc.invalidateQueries({ queryKey: queryKeys.overview });
    },
  });
}

export function usePositionMatches(positionId: number, enabled = true) {
  return useQuery({
    queryKey: queryKeys.positionMatches(positionId),
    queryFn: async () =>
      (
        await http.get<PositionOrderMatchRead[]>(
          `/api/v1/positions/${positionId}/matches`
        )
      ).data,
    enabled: !!positionId && enabled,
  });
}

export function usePositionCloseExecutions(
  positionId: number,
  enabled = true
) {
  return useQuery({
    queryKey: queryKeys.positionCloseExecutions(positionId),
    queryFn: async () =>
      (
        await http.get<PositionCloseExecutionRead[]>(
          `/api/v1/positions/${positionId}/close-executions`
        )
      ).data,
    enabled: !!positionId && enabled,
  });
}
