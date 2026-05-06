import { Card, Col, Row, Space, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { PageHeader } from "@/components/PageHeader";
import { KpiCard } from "@/components/KpiCard";
import { PnlText } from "@/components/PnlText";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { SideTag } from "@/components/SideTag";
import { ensurePosiTheme, POSI_PALETTE } from "@/theme/echartsTheme";
import { usePnl, usePositions, useOverview } from "@/api/hooks";
import {
  fmtCompact,
  fmtMoney,
  fmtPrice,
  fmtRelative,
} from "@/utils/format";

const { Text } = Typography;

ensurePosiTheme();

export function OverviewPage() {
  const overview = useOverview();
  const pnl = usePnl("30d");
  const positions = usePositions("merged");

  const equityOption = useMemo(() => {
    const points = pnl.data?.points ?? [];
    const dates = points.map((p) => p.snapshot_date);
    const values = points.map((p) => p.total_equity);
    return {
      grid: { left: 16, right: 16, top: 16, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (params: { axisValueLabel: string; value: number }[]) =>
          `${params[0].axisValueLabel}<br/><strong>${fmtMoney(
            params[0].value
          )} USDT</strong>`,
      },
      xAxis: { type: "category", data: dates, boundaryGap: false },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: (v: number) => fmtCompact(v) } },
      series: [
        {
          type: "line",
          data: values,
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2, color: POSI_PALETTE.primary },
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
      ],
    };
  }, [pnl.data]);

  const allocationOption = useMemo(() => {
    const top = (positions.data ?? [])
      .map((p) => ({
        name: p.canonical_symbol,
        value: Math.abs(p.notional || p.qty * p.mark_price || 0),
      }))
      .filter((x) => x.value > 0)
      .sort((a, b) => b.value - a.value)
      .slice(0, 6);
    return {
      tooltip: {
        trigger: "item",
        formatter: (p: { name: string; value: number; percent: number }) =>
          `${p.name}<br/><strong>${fmtCompact(p.value)}</strong> · ${p.percent.toFixed(
            1
          )}%`,
      },
      legend: { bottom: 0, icon: "circle" },
      series: [
        {
          type: "pie",
          radius: ["55%", "82%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: "#fff", borderWidth: 2, borderRadius: 6 },
          label: { show: false },
          labelLine: { show: false },
          data: top,
        },
      ],
    };
  }, [positions.data]);

  return (
    <Space direction="vertical" size={20} style={{ width: "100%" }}>
      <PageHeader
        title="总览"
        description={
          overview.data?.last_snapshot_at
            ? `最近快照 · ${fmtRelative(overview.data.last_snapshot_at)}`
            : "尚未生成快照"
        }
        extra={
          <Tag
            color="blue"
            style={{
              border: "none",
              background: "var(--posi-primary-soft)",
              color: "var(--posi-primary)",
              fontWeight: 500,
            }}
          >
            {overview.data?.total_accounts ?? 0} 个账户在管
          </Tag>
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label="总权益 (USDT)"
            value={fmtMoney(overview.data?.total_equity ?? 0)}
            hint={
              overview.data?.last_sync_at
                ? `同步于 ${fmtRelative(overview.data.last_sync_at)}`
                : "等待首次同步"
            }
            accent="primary"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label="未实现盈亏"
            value={
              <PnlText
                value={overview.data?.total_unrealized_pnl ?? 0}
                weight={600}
              />
            }
            hint="跨交易所聚合"
            accent={
              (overview.data?.total_unrealized_pnl ?? 0) >= 0 ? "up" : "down"
            }
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label="持仓数量"
            value={overview.data?.total_positions ?? 0}
            hint="按账户合计"
            accent="neutral"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label="账户数量"
            value={overview.data?.total_accounts ?? 0}
            hint="含模拟账户"
            accent="neutral"
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space size={12}>
                <span>权益走势</span>
                <Tag
                  style={{
                    margin: 0,
                    background: "var(--posi-surface-muted)",
                    border: "1px solid var(--posi-border)",
                    color: "var(--posi-text-secondary)",
                  }}
                >
                  近 30 日
                </Tag>
              </Space>
            }
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                数据基于每日 23:55 快照
              </Text>
            }
            bodyStyle={{ padding: 16 }}
            style={{ borderRadius: 12 }}
          >
            <AsyncBoundary
              loading={pnl.isLoading}
              error={pnl.error}
              empty={!pnl.data?.points?.length}
              emptyText="暂无快照，先去同步或写入快照"
            >
              <ReactECharts
                option={equityOption}
                theme="posi-light"
                notMerge
                style={{ height: 320 }}
              />
            </AsyncBoundary>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            title="持仓占比 Top 6"
            bodyStyle={{ padding: 16 }}
            style={{ borderRadius: 12, height: "100%" }}
          >
            <AsyncBoundary
              loading={positions.isLoading}
              error={positions.error}
              empty={!positions.data?.length}
              emptyText="暂无持仓"
            >
              <ReactECharts
                option={allocationOption}
                theme="posi-light"
                notMerge
                style={{ height: 320 }}
              />
            </AsyncBoundary>
          </Card>
        </Col>
      </Row>

      <Card
        title="主要持仓"
        bodyStyle={{ padding: 0 }}
        style={{ borderRadius: 12 }}
      >
        <AsyncBoundary
          loading={positions.isLoading}
          error={positions.error}
          empty={!positions.data?.length}
        >
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["合约", "方向", "数量", "均价", "标记价", "未实现盈亏"].map(
                  (h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        padding: "12px 20px",
                        fontSize: 11,
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        color: "var(--posi-text-muted)",
                        background: "var(--posi-surface-muted)",
                        borderBottom: "1px solid var(--posi-border)",
                      }}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {(positions.data ?? []).slice(0, 8).map((p) => (
                <tr key={p.canonical_symbol}>
                  <td style={tdStyle}>
                    <Text strong>{p.canonical_symbol}</Text>
                    <Text
                      type="secondary"
                      style={{ marginLeft: 8, fontSize: 12 }}
                    >
                      {p.accounts.length} 账户
                    </Text>
                  </td>
                  <td style={tdStyle}>
                    <SideTag side={p.side} />
                  </td>
                  <td style={{ ...tdStyle, fontFamily: "var(--posi-mono)" }}>
                    {p.qty.toLocaleString()}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: "var(--posi-mono)" }}>
                    {fmtPrice(p.avg_entry_price)}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: "var(--posi-mono)" }}>
                    {fmtPrice(p.mark_price)}
                  </td>
                  <td style={tdStyle}>
                    <PnlText value={p.unrealized_pnl} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AsyncBoundary>
      </Card>
    </Space>
  );
}

const tdStyle: React.CSSProperties = {
  padding: "14px 20px",
  borderBottom: "1px solid var(--posi-border)",
  fontSize: 13,
  color: "var(--posi-text)",
};
