import { useMemo, useState } from "react";
import { Card, Segmented, Space, Statistic, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { PageHeader } from "@/components/PageHeader";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { PnlText } from "@/components/PnlText";
import { ensurePosiTheme, POSI_PALETTE } from "@/theme/echartsTheme";
import { usePnl } from "@/api/hooks";
import { fmtCompact, fmtMoney } from "@/utils/format";

const { Text } = Typography;

ensurePosiTheme();

const RANGES = [
  { label: "近 7 日", value: "7d" },
  { label: "近 30 日", value: "30d" },
  { label: "近 90 日", value: "90d" },
  { label: "近 365 日", value: "365d" },
];

export function PnlPage() {
  const [range, setRange] = useState("30d");
  const pnl = usePnl(range);

  const points = pnl.data?.points ?? [];

  const stats = useMemo(() => {
    if (!points.length) {
      return { first: 0, last: 0, change: 0, changePct: 0, peak: 0, trough: 0 };
    }
    const first = points[0].total_equity;
    const last = points[points.length - 1].total_equity;
    const equities = points.map((p) => p.total_equity);
    return {
      first,
      last,
      change: last - first,
      changePct: first === 0 ? 0 : (last - first) / first,
      peak: Math.max(...equities),
      trough: Math.min(...equities),
    };
  }, [points]);

  const option = useMemo(() => {
    const dates = points.map((p) => p.snapshot_date);
    const equities = points.map((p) => p.total_equity);
    const upnl = points.map((p) => p.total_unrealized_pnl);

    return {
      grid: { left: 16, right: 24, top: 32, bottom: 56, containLabel: true },
      legend: { top: 0, left: 0 },
      tooltip: {
        trigger: "axis",
        formatter: (
          params: { axisValueLabel: string; seriesName: string; value: number }[]
        ) =>
          `<div style="min-width:160px"><strong>${
            params[0]?.axisValueLabel
          }</strong><br/>${params
            .map(
              (p) =>
                `${p.seriesName}: <strong>${fmtMoney(p.value)} USDT</strong>`
            )
            .join("<br/>")}</div>`,
      },
      xAxis: { type: "category", data: dates, boundaryGap: false },
      yAxis: [
        {
          type: "value",
          scale: true,
          name: "权益",
          nameTextStyle: { color: POSI_PALETTE.textMuted, fontSize: 11 },
          axisLabel: { formatter: (v: number) => fmtCompact(v) },
        },
        {
          type: "value",
          scale: true,
          name: "未实现盈亏",
          nameTextStyle: { color: POSI_PALETTE.textMuted, fontSize: 11 },
          splitLine: { show: false },
          axisLabel: { formatter: (v: number) => fmtCompact(v) },
        },
      ],
      series: [
        {
          name: "权益",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: equities,
          lineStyle: { color: POSI_PALETTE.primary, width: 2 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(30,58,138,0.18)" },
                { offset: 1, color: "rgba(30,58,138,0)" },
              ],
            },
          },
        },
        {
          name: "未实现盈亏",
          type: "bar",
          yAxisIndex: 1,
          data: upnl,
          itemStyle: {
            color: (p: { data: number }) =>
              p.data >= 0 ? "rgba(22,163,74,0.55)" : "rgba(220,38,38,0.55)",
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: 16,
        },
      ],
    };
  }, [points]);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="盈亏"
        description="基于每日快照的权益曲线与未实现盈亏柱状对照"
      />

      <Segmented
        value={range}
        onChange={(v) => setRange(String(v))}
        options={RANGES}
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: 16,
        }}
      >
        <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
          <Statistic
            title="期初权益"
            value={stats.first}
            precision={2}
            suffix=" USDT"
          />
        </Card>
        <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
          <Statistic
            title="当前权益"
            value={stats.last}
            precision={2}
            suffix=" USDT"
          />
        </Card>
        <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
          <Text
            style={{
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              fontSize: 11,
              color: "var(--posi-text-muted)",
              fontWeight: 500,
            }}
          >
            区间盈亏
          </Text>
          <div style={{ marginTop: 8, fontSize: 22 }}>
            <PnlText value={stats.change} weight={600} />
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {(stats.changePct * 100).toFixed(2)}%
          </Text>
        </Card>
        <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
          <Statistic
            title="区间峰值"
            value={stats.peak}
            precision={2}
            suffix=" USDT"
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            谷值 {fmtMoney(stats.trough)}
          </Text>
        </Card>
      </div>

      <Card
        title="权益曲线"
        bodyStyle={{ padding: 16 }}
        style={{ borderRadius: 12 }}
      >
        <AsyncBoundary
          loading={pnl.isLoading}
          error={pnl.error}
          empty={!points.length}
          emptyText="暂无数据，等待每日快照生成或从「手动录入」补录"
        >
          <ReactECharts
            theme="posi-light"
            option={option}
            notMerge
            style={{ height: 420 }}
          />
        </AsyncBoundary>
      </Card>
    </Space>
  );
}
