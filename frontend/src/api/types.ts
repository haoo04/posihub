/* Types mirroring backend pydantic schemas. Keep in sync with
 * backend/app/schemas/*. */

export type DataSource = "api" | "manual" | "simulated";
export type PositionSide = "long" | "short" | "net";
export type PositionOrderStatus = "open" | "partial" | "closed";
export type InstrumentType = "spot" | "perp" | "futures";
export type AccountType =
  | "spot"
  | "usdt_perp"
  | "coin_perp"
  | "futures"
  | "funding"
  | "simulated";

export interface Health {
  status: string;
  app: string;
  version: string;
}

export interface Overview {
  total_equity: number;
  total_unrealized_pnl: number;
  total_positions: number;
  total_accounts: number;
  last_snapshot_at: string | null;
  last_sync_at: string | null;
}

export interface Exchange {
  id: number;
  name: string;
  enabled: boolean;
  created_at: string;
}

export interface Account {
  id: number;
  exchange_id: number;
  account_name: string;
  account_type: AccountType;
  is_simulated: boolean;
  enabled: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  consecutive_failures: number;
  created_at: string;
  api_key_masked: string | null;
}

export interface AccountCreate {
  exchange_id: number;
  account_name: string;
  account_type: AccountType;
  api_key?: string | null;
  api_secret?: string | null;
  passphrase?: string | null;
  is_simulated: boolean;
  enabled: boolean;
}

export interface AccountSyncStatus {
  account_id: number;
  success: boolean;
  message: string;
  synced_at: string;
}

export interface PositionSplit {
  id: number;
  account_id: number;
  canonical_symbol: string;
  side: PositionSide;
  qty: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  leverage: number;
  margin_mode: string | null;
  updated_at: string;
  source: DataSource;
  account_type?: AccountType | null;
  pnl_asset?: string | null;
}

export interface PositionMerged {
  canonical_symbol: string;
  side: PositionSide;
  qty: number;
  avg_entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  notional: number;
  accounts: number[];
}

export interface PnlPoint {
  snapshot_date: string;
  total_equity: number;
  total_unrealized_pnl: number;
}

export interface PnlSeries {
  range: string;
  asset: string;
  points: PnlPoint[];
}

export interface AccountSnapshot {
  id: number;
  snapshot_date: string;
  account_id: number;
  asset: string;
  total_equity: number;
  total_unrealized_pnl: number;
  total_available: number;
  source: DataSource;
  created_at: string;
}

export interface PositionSnapshot {
  id: number;
  snapshot_date: string;
  account_id: number;
  canonical_symbol: string;
  side: PositionSide;
  qty: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  source: DataSource;
  created_at: string;
}

export interface ManualBalanceItem {
  asset: string;
  equity: number;
  available?: number;
  frozen?: number;
}

export interface ManualPositionItem {
  canonical_symbol: string;
  side: PositionSide;
  qty: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl?: number;
}

export interface ManualSnapshotCreate {
  account_id: number;
  snapshot_date: string;
  asset: string;
  total_equity?: number | null;
  total_unrealized_pnl?: number;
  total_available?: number;
  balances: ManualBalanceItem[];
  positions: ManualPositionItem[];
  operator?: string;
}

export interface ManualSnapshotResult {
  account_id: number;
  snapshot_date: string;
  accounts_written: number;
  positions_written: number;
  balances_written: number;
}

export interface SymbolMapping {
  id: number;
  exchange: string;
  raw_symbol: string;
  canonical_symbol: string;
  base_asset: string;
  quote_asset: string;
  instrument_type: InstrumentType;
  contract_size: number;
  is_active: boolean;
  created_at: string;
}

export interface PositionOrderBase {
  source: DataSource;
  source_order_id: string | null;
  open_qty: number;
  entry_price: number;
  leverage: number;
  margin: number | null;
  mmr: number | null;
  liquidation_price: number | null;
}

export interface PositionOrderCreate extends PositionOrderBase {
  position_id: number;
}

export interface PositionOrderRead extends PositionOrderBase {
  id: number;
  position_id: number;
  status: PositionOrderStatus;
  remaining_qty: number;
  created_at: string;
  updated_at: string;
}

export interface PositionOrderWithPnL extends PositionOrderRead {
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  mark_price: number;
  realized_pnl: number;
  close_price?: number | null;
  pnl_asset?: string | null;
  unrealized_pnl_native?: number | null;
  unrealized_pnl_usdt?: number | null;
  realized_pnl_native?: number | null;
  realized_pnl_usdt?: number | null;
}

export interface PositionOrderUpdate {
  open_qty?: number;
  remaining_qty?: number;
  entry_price?: number;
  leverage?: number;
  margin?: number | null;
  mmr?: number | null;
  liquidation_price?: number | null;
  status?: PositionOrderStatus;
}

export interface PositionCloseRequest {
  close_qty: number;
  close_price: number;
  source?: DataSource;
  source_order_id?: string | null;
}

export interface SpecifiedCloseLeg {
  open_order_id: number;
  qty: number;
}

export interface SpecifiedCloseRequest {
  close_qty: number;
  close_price: number;
  legs: SpecifiedCloseLeg[];
  source?: DataSource;
  source_order_id?: string | null;
}

export interface PositionOrderMatchRead {
  id: number;
  open_order_id: number;
  close_order_id: number;
  matched_qty: number;
  open_price: number;
  close_price: number;
  realized_pnl: number;
  matched_at: string;
}

export interface PositionCloseExecutionRead {
  id: number;
  position_id: number;
  close_qty: number;
  close_price: number;
  source: DataSource;
  source_order_id: string | null;
  realized_pnl: number;
  created_at: string;
}

export interface FifoCloseResponse {
  execution: PositionCloseExecutionRead;
  matches: PositionOrderMatchRead[];
  affected_orders: PositionOrderRead[];
  realized_pnl: number;
}
