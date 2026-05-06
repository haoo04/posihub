import * as echarts from "echarts/core";

export const POSI_PALETTE = {
  primary: "#1e3a8a",
  primarySoft: "rgba(30, 58, 138, 0.10)",
  accent: "#0ea5e9",
  up: "#16a34a",
  down: "#dc2626",
  text: "#0f172a",
  textMuted: "#94a3b8",
  border: "#e6e8ef",
  surface: "#ffffff",
} as const;

/**
 * Light, financial chart theme.
 * Registered once at app startup as `posi-light` and used everywhere.
 */
export const POSI_ECHARTS_THEME = {
  color: [
    POSI_PALETTE.primary,
    POSI_PALETTE.accent,
    "#6366f1",
    "#10b981",
    "#f59e0b",
    "#8b5cf6",
    "#ef4444",
  ],
  backgroundColor: "transparent",
  textStyle: {
    fontFamily:
      '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
    color: POSI_PALETTE.text,
  },
  title: {
    textStyle: { color: POSI_PALETTE.text, fontWeight: 600 },
    subtextStyle: { color: POSI_PALETTE.textMuted },
  },
  grid: {
    left: 48,
    right: 24,
    top: 40,
    bottom: 40,
    containLabel: true,
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: POSI_PALETTE.border } },
    axisTick: { show: false },
    axisLabel: { color: POSI_PALETTE.textMuted, fontSize: 12 },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: POSI_PALETTE.textMuted, fontSize: 12 },
    splitLine: { lineStyle: { color: POSI_PALETTE.border, type: "dashed" } },
  },
  legend: {
    textStyle: { color: POSI_PALETTE.textMuted },
    itemWidth: 10,
    itemHeight: 10,
    icon: "circle",
  },
  tooltip: {
    backgroundColor: "#ffffff",
    borderColor: POSI_PALETTE.border,
    borderWidth: 1,
    textStyle: { color: POSI_PALETTE.text, fontSize: 12 },
    extraCssText:
      "box-shadow: 0 6px 32px rgba(15,23,42,0.08); border-radius: 8px;",
  },
  line: {
    smooth: true,
    symbol: "circle",
    symbolSize: 4,
    showSymbol: false,
    lineStyle: { width: 2 },
  },
  bar: {
    itemStyle: { borderRadius: [4, 4, 0, 0] },
  },
  pie: {
    label: { color: POSI_PALETTE.textMuted },
    labelLine: { lineStyle: { color: POSI_PALETTE.border } },
  },
};

let registered = false;

export function ensurePosiTheme() {
  if (!registered) {
    echarts.registerTheme("posi-light", POSI_ECHARTS_THEME);
    registered = true;
  }
}
