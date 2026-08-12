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
import { useBreakpoint } from "@/hooks/useBreakpoint";
import {
  fmtCompact,
  fmtMoney,
  fmtPrice,
  fmtRelative,
} from "@/utils/format";
import { useLocale } from "@/i18n/LocaleContext";

const { Text } = Typography;

ensurePosiTheme();

export function OverviewPage() {
  const { t } = useLocale();
  const { isMobile } = useBreakpoint();
  const overview = useOverview();
  const pnl = usePnl("30d");
  const positions = usePositions("merged");

  const chartH = isMobile ? 240 : 320;
  const pieH = isMobile ? 260 : 320;

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

  const realizedTotal = useMemo(
    () =>
      (positions.data ?? []).reduce(
        (sum, p) => sum + (p.realized_pnl ?? 0),
        0
      ),
    [positions.data]
  );

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
      legend: { bottom: isMobile ? 4 : 0, icon: "circle", itemWidth: 8 },
      series: [
        {
          type: "pie",
          radius: isMobile ? ["48%", "78%"] : ["55%", "82%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: "#fff", borderWidth: 2, borderRadius: 6 },
          label: { show: false },
          labelLine: { show: false },
          data: top,
        },
      ],
    };
  }, [positions.data, isMobile]);

  return (
    <Space direction="vertical" size={isMobile ? 16 : 20} style={{ width: "100%" }}>
      <PageHeader
        title={t("overview.title")}
        description={
          overview.data?.last_snapshot_at
            ? t("overview.latestSnapshot", {
                time: fmtRelative(overview.data.last_snapshot_at),
              })
            : t("overview.noSnapshot")
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
            {t("overview.managedAccounts", {
              count: overview.data?.total_accounts ?? 0,
            })}
          </Tag>
        }
      />

      <Row gutter={isMobile ? [12, 12] : [16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label={t("overview.totalEquity")}
            loading={overview.isLoading}
            value={fmtMoney(overview.data?.total_equity ?? 0)}
            hint={
              overview.data?.last_sync_at
                ? t("overview.syncedAt", {
                    time: fmtRelative(overview.data.last_sync_at),
                  })
                : t("overview.waitingFirstSync")
            }
            accent="primary"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label={t("overview.unrealizedPnl")}
            loading={overview.isLoading || positions.isLoading}
            value={
              <PnlText
                value={overview.data?.total_unrealized_pnl ?? 0}
                weight={600}
              />
            }
            hint={
              <span>
                {t("overview.realized")} <PnlText value={realizedTotal} />
              </span>
            }
            accent={
              (overview.data?.total_unrealized_pnl ?? 0) >= 0 ? "up" : "down"
            }
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label={t("overview.positionCount")}
            loading={overview.isLoading}
            value={overview.data?.total_positions ?? 0}
            hint={t("overview.byAccount")}
            accent="neutral"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            label={t("overview.accountCount")}
            loading={overview.isLoading}
            value={overview.data?.total_accounts ?? 0}
            hint={t("overview.includingSimulated")}
            accent="neutral"
          />
        </Col>
      </Row>

      <Row gutter={isMobile ? [12, 12] : [16, 16]}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space size={12}>
                <span>{t("overview.equityTrend")}</span>
                <Tag
                  style={{
                    margin: 0,
                    background: "var(--posi-surface-muted)",
                    border: "1px solid var(--posi-border)",
                    color: "var(--posi-text-secondary)",
                  }}
                >
                  {t("overview.last30Days")}
                </Tag>
              </Space>
            }
            extra={
              !isMobile ? (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {t("overview.dailySnapshotNote")}
                </Text>
              ) : null
            }
            bodyStyle={{ padding: 16 }}
            style={{ borderRadius: 12 }}
          >
            <AsyncBoundary
              loading={pnl.isLoading}
              error={pnl.error}
              empty={!pnl.data?.points?.length}
              emptyText={t("overview.noSnapshots")}
            >
              <ReactECharts
                option={equityOption}
                theme="posi-light"
                notMerge
                style={{ height: chartH }}
              />
            </AsyncBoundary>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            title={t("overview.allocationTop")}
            bodyStyle={{ padding: 16 }}
            style={{ borderRadius: 12, height: "100%" }}
          >
            <AsyncBoundary
              loading={positions.isLoading}
              error={positions.error}
              empty={!positions.data?.length}
              emptyText={t("overview.noPositions")}
            >
              <ReactECharts
                option={allocationOption}
                theme="posi-light"
                notMerge
                style={{ height: pieH }}
              />
            </AsyncBoundary>
          </Card>
        </Col>
      </Row>

      <Card
        title={t("overview.mainPositions")}
        bodyStyle={{ padding: 0 }}
        style={{ borderRadius: 12 }}
      >
        <AsyncBoundary
          loading={positions.isLoading}
          error={positions.error}
          empty={!positions.data?.length}
        >
          <div className={isMobile ? "posi-table-wrap" : undefined}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: isMobile ? 520 : undefined }}>
            <thead>
              <tr>
                {[
                  t("overview.contract"),
                  t("overview.side"),
                  t("overview.qty"),
                  t("overview.avgPrice"),
                  t("overview.markPrice"),
                  t("overview.unrealizedPnl"),
                  t("overview.realized"),
                ].map(
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
                      {t("overview.accounts", { count: p.accounts.length })}
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
                  <td style={tdStyle}>
                    <PnlText value={p.realized_pnl} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
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
