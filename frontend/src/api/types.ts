/* Types mirroring backend pydantic schemas. Keep in sync with
 * backend/app/schemas/*. */

export type DataSource = "api" | "manual" | "simulated";
export type PositionSide = "long" | "short" | "net";
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
  leverage: number;
  margin_mode: string | null;
  updated_at: string;
  source: DataSource;
}

export interface PositionMerged {
  canonical_symbol: string;
  side: PositionSide;
  qty: number;
  avg_entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
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
