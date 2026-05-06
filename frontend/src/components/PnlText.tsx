import { fmtSigned, pnlClass } from "@/utils/format";

interface Props {
  value: number | null | undefined;
  suffix?: string;
  monospace?: boolean;
  weight?: 400 | 500 | 600;
}

export function PnlText({
  value,
  suffix,
  monospace = true,
  weight = 500,
}: Props) {
  return (
    <span
      className={`${pnlClass(value)} ${monospace ? "posi-numeric" : ""}`}
      style={{ fontWeight: weight }}
    >
      {fmtSigned(value)}
      {suffix ? ` ${suffix}` : ""}
    </span>
  );
}
