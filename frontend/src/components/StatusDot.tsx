interface Props {
  status: "ok" | "error" | "idle" | "syncing";
  label?: string;
}

const COLORS: Record<Props["status"], { color: string; ring: string }> = {
  ok: { color: "#16a34a", ring: "rgba(22,163,74,0.18)" },
  error: { color: "#dc2626", ring: "rgba(220,38,38,0.18)" },
  syncing: { color: "#0ea5e9", ring: "rgba(14,165,233,0.18)" },
  idle: { color: "#94a3b8", ring: "rgba(148,163,184,0.18)" },
};

export function StatusDot({ status, label }: Props) {
  const c = COLORS[status];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: c.color,
          boxShadow: `0 0 0 4px ${c.ring}`,
        }}
      />
      {label && (
        <span style={{ color: "var(--posi-text-secondary)", fontSize: 13 }}>
          {label}
        </span>
      )}
    </span>
  );
}
