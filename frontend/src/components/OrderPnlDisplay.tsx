import { Tooltip } from "antd";
import { PnlText } from "./PnlText";
import { fmtQty, fmtSigned } from "@/utils/format";

interface OrderPnlDisplayProps {
  /** Legacy/native settlement value, shown only in the coin tooltip. */
  nativeValue: number | null | undefined;
  /** Canonical primary value in USDT. */
  usdtValue: number | null | undefined;
  asset: string | null | undefined;
  coinMargined: boolean;
}

function formatNative(value: number, asset: string) {
  const abs = Math.abs(value);
  const digits = abs > 0 && abs < 0.0001 ? 8 : abs < 1 ? 6 : 4;
  const body = fmtQty(abs, digits);
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${body} ${asset}`;
}

export function OrderPnlDisplay({
  nativeValue,
  usdtValue,
  asset,
  coinMargined,
}: OrderPnlDisplayProps) {
  const native = nativeValue ?? 0;
  const usdt = usdtValue ?? 0;
  const primary = <PnlText value={usdtValue ?? nativeValue} suffix="USDT" />;

  if (!coinMargined || !asset) return primary;

  return (
    <Tooltip title={`结算币: ${formatNative(native, asset)} · ${fmtSigned(usdt)} USDT`}>
      {primary}
    </Tooltip>
  );
}

interface OrderMarginDisplayProps {
  value: number | null | undefined;
  asset: string | null | undefined;
  coinMargined: boolean;
}

export function OrderMarginDisplay({
  value,
  asset,
  coinMargined,
}: OrderMarginDisplayProps) {
  if (value === null || value === undefined) {
    return <>—</>;
  }
  if (coinMargined && asset) {
    return (
      <span className="posi-numeric">
        {fmtQty(value, 8)} {asset}
      </span>
    );
  }
  return <span className="posi-numeric">{fmtQty(value, 4)}</span>;
}
