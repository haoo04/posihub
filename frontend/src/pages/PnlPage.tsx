import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Segmented,
  Skeleton,
  Space,
  Statistic,
  Typography,
} from "antd";
import { Link } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import { PageHeader } from "@/components/PageHeader";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { PnlText } from "@/components/PnlText";
import { ensurePosiTheme, POSI_PALETTE } from "@/theme/echartsTheme";
import { usePnl } from "@/api/hooks";
import { useBreakpoint } from "@/hooks/useBreakpoint";
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
  const { isMobile } = useBreakpoint();
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
      grid: {
        left: isMobile ? 8 : 16,
        right: isMobile ? 8 : 24,
        top: 32,
        bottom: isMobile ? 68 : 56,
        containLabel: true,
      },
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
          name: "未实现盈亏 (USDT)",
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
        name: "未实现盈亏 (USDT)",
          type: "bar",
          yAxisIndex: 1,
          data: upnl,
          itemStyle: {
            color: (p: { data: number }) =>
              p.data >= 0 ? "rgba(22,163,74,0.55)" : "rgba(220,38,38,0.55)",
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: isMobile ? 10 : 16,
        },
      ],
    };
  }, [points, isMobile]);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="盈亏"
        description="基于每日快照的 USDT 权益曲线与未实现盈亏柱状对照"
      />

      <Segmented
        block={isMobile}
        value={range}
        onChange={(v) => setRange(String(v))}
        options={RANGES}
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: isMobile
            ? "repeat(2, minmax(0, 1fr))"
            : "repeat(auto-fit, minmax(200px, 1fr))",
          gap: isMobile ? 12 : 16,
        }}
      >
        <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
          <Statistic
            title="期初权益"
            loading={pnl.isLoading}
            value={stats.first}
            precision={2}
            suffix=" USDT"
          />
        </Card>
        <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
          <Statistic
            title="当前权益"
            loading={pnl.isLoading}
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
            {pnl.isLoading ? (
              <Skeleton.Button active size="small" style={{ width: 96, height: 24 }} />
            ) : (
              <PnlText value={stats.change} weight={600} />
            )}
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {pnl.isLoading ? "—" : `${(stats.changePct * 100).toFixed(2)}%`}
          </Text>
        </Card>
        <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
          <Statistic
            title="区间峰值"
            loading={pnl.isLoading}
            value={stats.peak}
            precision={2}
            suffix=" USDT"
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {pnl.isLoading ? "谷值 —" : `谷值 ${fmtMoney(stats.trough)}`}
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
          emptyText={
            <Space direction="vertical" align="center" size={12}>
              <Text type="secondary">
                暂无数据，等待每日快照生成或从「手动录入」补录
              </Text>
              <Space>
                <Link to="/accounts">
                  <Button type="primary">去同步账户</Button>
                </Link>
                <Link to="/manual">
                  <Button>手动录入</Button>
                </Link>
              </Space>
            </Space>
          }
        >
          <ReactECharts
            theme="posi-light"
            option={option}
            notMerge
            style={{ height: isMobile ? 320 : 420 }}
          />
        </AsyncBoundary>
      </Card>
    </Space>
  );
}
