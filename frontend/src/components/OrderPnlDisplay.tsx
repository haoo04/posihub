import { Tooltip } from "antd";
import { PnlText } from "./PnlText";
import { fmtQty, fmtSigned } from "@/utils/format";

interface OrderPnlDisplayProps {
  /** Primary value in settlement coin for coin-margined; USDT otherwise. */
  nativeValue: number | null | undefined;
  /** USDT equivalent (hover for coin-margined). */
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
  if (!coinMargined || !asset) {
    return <PnlText value={usdtValue ?? nativeValue} />;
  }

  const native = nativeValue ?? 0;
  const usdt = usdtValue ?? 0;
  const body = (
    <span className="posi-numeric" style={{ fontWeight: 500 }}>
      {formatNative(native, asset)}
    </span>
  );

  return (
    <Tooltip title={`≈ ${fmtSigned(usdt)} USDT`}>
      {body}
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
