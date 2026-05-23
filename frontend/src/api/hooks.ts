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
  ManualSnapshotCreate,
  ManualSnapshotResult,
  Overview,
  PnlSeries,
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
  accountSnapshots: (params: Record<string, unknown> = {}) =>
    ["snapshots", "accounts", params] as const,
  positionSnapshots: (params: Record<string, unknown> = {}) =>
    ["snapshots", "positions", params] as const,
  symbols: ["symbols"] as const,
};

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
