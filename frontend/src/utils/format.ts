import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import "dayjs/locale/zh-cn";

dayjs.extend(relativeTime);
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.locale("zh-cn");

const MONEY_FMT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const COMPACT_FMT = new Intl.NumberFormat("en-US", {
  notation: "compact",
  minimumFractionDigits: 1,
  maximumFractionDigits: 2,
});

export function fmtMoney(value: number | null | undefined, asset = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const formatted = MONEY_FMT.format(value);
  return asset ? `${formatted} ${asset}` : formatted;
}

export function fmtCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) < 10_000) return MONEY_FMT.format(value);
  return COMPACT_FMT.format(value);
}

export function fmtSigned(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const formatted = MONEY_FMT.format(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

export function fmtPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${(Math.abs(value) * 100).toFixed(2)}%`;
}

export function fmtQty(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

export function fmtPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 100) {
    return MONEY_FMT.format(value);
  }
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return dayjs.utc(value).tz("Asia/Shanghai").format("YYYY-MM-DD HH:mm:ss");
}

export function fmtRelative(value: string | null | undefined): string {
  if (!value) return "—";
  return dayjs.utc(value).tz("Asia/Shanghai").fromNow();
}

export function pnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "posi-muted";
  return value > 0 ? "posi-up" : "posi-down";
}
