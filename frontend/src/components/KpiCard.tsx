import { Card, Grid, Typography } from "antd";
import type { ReactNode } from "react";

const { Text } = Typography;
const { useBreakpoint } = Grid;

interface Props {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  accent?: "neutral" | "up" | "down" | "primary";
}

const ACCENT_BAR: Record<NonNullable<Props["accent"]>, string> = {
  neutral: "linear-gradient(180deg, #cbd5e1 0%, #94a3b8 100%)",
  primary: "linear-gradient(180deg, #1e3a8a 0%, #0ea5e9 100%)",
  up: "linear-gradient(180deg, #16a34a 0%, #22c55e 100%)",
  down: "linear-gradient(180deg, #dc2626 0%, #f97316 100%)",
};

export function KpiCard({ label, value, hint, accent = "primary" }: Props) {
  const screens = useBreakpoint();
  const mdUp = !!screens.md;
  return (
    <Card
      bodyStyle={{ padding: mdUp ? 20 : 16, position: "relative" }}
      style={{ borderRadius: 12, overflow: "hidden" }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 18,
          bottom: 18,
          width: 3,
          borderRadius: 4,
          background: ACCENT_BAR[accent],
        }}
      />
      <Text
        style={{
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          fontSize: 11,
          color: "var(--posi-text-muted)",
          fontWeight: 500,
        }}
      >
        {label}
      </Text>
      <div
        style={{
          marginTop: 8,
          fontFamily: "var(--posi-mono)",
          fontVariantNumeric: "tabular-nums",
          fontSize: mdUp ? 26 : 22,
          fontWeight: 600,
          letterSpacing: "-0.01em",
          color: "var(--posi-text)",
        }}
      >
        {value}
      </div>
      {hint !== undefined && (
        <div style={{ marginTop: 6, fontSize: 12, color: "var(--posi-text-muted)" }}>
          {hint}
        </div>
      )}
    </Card>
  );
}
