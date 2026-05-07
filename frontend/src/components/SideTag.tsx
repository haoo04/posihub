import { Tag } from "antd";
import type { PositionSide } from "@/api/types";

const STYLES: Record<PositionSide, { color: string; bg: string; label: string }> = {
  long: { color: "#15803d", bg: "#ecfdf5", label: "LONG" },
  short: { color: "#b91c1c", bg: "#fef2f2", label: "SHORT" },
  net: { color: "#475569", bg: "#f1f5f9", label: "NET" },
};

export function SideTag({ side }: { side: PositionSide }) {
  const s = STYLES[side];
  return (
    <Tag
      style={{
        color: s.color,
        background: s.bg,
        border: "none",
        fontWeight: 600,
        letterSpacing: "0.06em",
        fontSize: 11,
        borderRadius: 4,
        padding: "0 8px",
        margin: 0,
      }}
    >
      {s.label}
    </Tag>
  );
}
