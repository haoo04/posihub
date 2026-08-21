import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import type { SorterResult } from "antd/es/table/interface";
import { DownloadOutlined, InfoCircleOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { PageHeader } from "@/components/PageHeader";
import { KpiCard } from "@/components/KpiCard";
import { PnlText } from "@/components/PnlText";
import { SideTag } from "@/components/SideTag";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { ensurePosiTheme, POSI_PALETTE } from "@/theme/echartsTheme";
import {
  useAccounts,
  usePerformanceBreakdown,
  usePerformanceEquity,
  usePerformanceRealized,
  usePerformanceSummary,
  usePerformanceTrades,
} from "@/api/hooks";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { exportCsv } from "@/utils/csv";
import { fmtCompact, fmtMoney, fmtPrice } from "@/utils/format";
import dayjs from "dayjs";
import type {
  BreakdownDimension,
  BreakdownRowRead,
  TradeRowRead,
  TradeSortField,
} from "@/api/types";

const { Text } = Typography;

ensurePosiTheme();

const RANGES = [
  { label: "近 7 日", value: "7d" },
  { label: "近 30 日", value: "30d" },
  { label: "近 90 日", value: "90d" },
  { label: "近 365 日", value: "365d" },
];

const DIMENSIONS: { label: string; value: BreakdownDimension }[] = [
  { label: "按合约", value: "symbol" },
  { label: "按账户", value: "account" },
  { label: "按方向", value: "side" },
  { label: "按交易所", value: "exchange" },
];

const SIDE_LABEL: Record<string, string> = {
  long: "多",
  short: "空",
  net: "净",
};

const PAGE_SIZE = 20;

function fmtHold(hours: number | null): string {
  if (hours === null || hours === undefined || Number.isNaN(hours)) return "—";
  if (hours < 24) return `${hours.toFixed(1)} 小时`;
  return `${(hours / 24).toFixed(1)} 天`;
}

function fmtRatio(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

function MetricHint({ title, text }: { title: string; text: string }) {
  return (
    <Tooltip title={text}>
      <InfoCircleOutlined
        style={{ marginLeft: 4, color: "var(--posi-text-muted)", fontSize: 12 }}
        aria-label={title}
      />
    </Tooltip>
  );
}

export function PerformancePage() {
  const { isMobile } = useBreakpoint();
  const accounts = useAccounts();
  const [range, setRange] = useState("30d");
  const [accountIds, setAccountIds] = useState<number[]>([]);
  const [includeSimulated, setIncludeSimulated] = useState(false);

  const queryParams = useMemo(
    () => ({
      range,
      asset: "USDT",
      account_ids: accountIds.length ? accountIds : undefined,
      include_simulated: includeSimulated,
    }),
    [range, accountIds, includeSimulated]
  );

  const [dimension, setDimension] = useState<BreakdownDimension>("symbol");
  const [tradePage, setTradePage] = useState(1);
  const [tradeSort, setTradeSort] = useState<{
    field: TradeSortField;
    desc: boolean;
  }>({ field: "closed_at", desc: true });

  const summary = usePerformanceSummary(queryParams);
  const equity = usePerformanceEquity(queryParams);
  const realized = usePerformanceRealized(queryParams);
  const breakdown = usePerformanceBreakdown(dimension, queryParams);
  const trades = usePerformanceTrades({
    ...queryParams,
    page: tradePage,
    page_size: PAGE_SIZE,
    sort_field: tradeSort.field,
    sort_desc: tradeSort.desc,
  });

  const data = summary.data;
  const points = equity.data?.points ?? [];
  const realizedPoints = realized.data?.points ?? [];
  const breakdownRows = breakdown.data?.rows ?? [];
  const tradeRows = trades.data?.items ?? [];

  const onExportTrades = () => {
    if (!tradeRows.length) return;
    exportCsv<TradeRowRead>(
      `trades-${range}-${dayjs().format("YYYYMMDD-HHmm")}.csv`,
      [
        {
          header: "平仓时间",
          value: (r) =>
            r.closed_at ? dayjs(r.closed_at).format("YYYY-MM-DD HH:mm:ss") : "",
        },
        { header: "账户", value: (r) => r.account_name },
        { header: "合约", value: (r) => r.canonical_symbol },
        { header: "方向", value: (r) => r.side },
        { header: "平仓数量", value: (r) => r.close_qty },
        { header: "平仓价", value: (r) => r.close_price },
        { header: "已实现盈亏", value: (r) => r.realized_pnl },
        {
          header: "持仓时长(小时)",
          value: (r) =>
            r.hold_duration_hours === null
              ? ""
              : r.hold_duration_hours.toFixed(2),
        },
        { header: "来源", value: (r) => r.source },
      ],
      tradeRows
    );
  };

  const tradeColumns: ColumnsType<TradeRowRead> = useMemo(
    () => [
      {
        title: "平仓时间",
        dataIndex: "closed_at",
        key: "closed_at",
        sorter: true,
        defaultSortOrder: "descend",
        render: (v: string | null) =>
          v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "—",
      },
      {
        title: "账户",
        dataIndex: "account_name",
        key: "account_name",
      },
      {
        title: "合约",
        dataIndex: "canonical_symbol",
        key: "canonical_symbol",
      },
      {
        title: "方向",
        dataIndex: "side",
        key: "side",
        render: (side: TradeRowRead["side"]) => <SideTag side={side} />,
      },
      {
        title: "平仓数量",
        dataIndex: "close_qty",
        key: "close_qty",
        align: "right",
        sorter: true,
        render: (v: number) => v,
      },
      {
        title: "平仓价",
        dataIndex: "close_price",
        key: "close_price",
        align: "right",
        render: (v: number) => fmtPrice(v),
      },
      {
        title: "已实现盈亏",
        dataIndex: "realized_pnl",
        key: "realized_pnl",
        align: "right",
        sorter: true,
        render: (v: number) => <PnlText value={v} />,
      },
      {
        title: "持仓时长",
        dataIndex: "hold_duration_hours",
        key: "hold_duration_hours",
        align: "right",
        render: (v: number | null) => fmtHold(v),
      },
    ],
    []
  );

  const onTradeTableChange = (
    pagination: TablePaginationConfig,
    _filters: unknown,
    sorter: SorterResult<TradeRowRead> | SorterResult<TradeRowRead>[]
  ) => {
    const s = Array.isArray(sorter) ? sorter[0] : sorter;
    const field = String(s?.field ?? "closed_at");
    if (
      s?.order &&
      (field === "closed_at" ||
        field === "realized_pnl" ||
        field === "close_qty")
    ) {
      setTradeSort({ field, desc: s.order === "descend" });
    }
    if (pagination.current) setTradePage(pagination.current);
  };

  const realizedOption = useMemo(() => {
    const dates = realizedPoints.map((p) => p.trade_date);
    const values = realizedPoints.map((p) => p.realized_pnl);
    return {
      grid: {
        left: isMobile ? 8 : 16,
        right: isMobile ? 8 : 16,
        top: 24,
        bottom: isMobile ? 48 : 40,
        containLabel: true,
      },
      tooltip: {
        trigger: "axis",
        formatter: (
          params: { axisValueLabel: string; value: number }[]
        ) =>
          `${params[0]?.axisValueLabel}<br/><strong>${fmtMoney(
            params[0]?.value
          )} USDT</strong>`,
      },
      xAxis: { type: "category", data: dates },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { formatter: (v: number) => fmtCompact(v) },
      },
      series: [
        {
          name: "当日已实现",
          type: "bar",
          data: values,
          itemStyle: {
            color: (p: { data: number }) =>
              p.data >= 0 ? POSI_PALETTE.up : POSI_PALETTE.down,
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: isMobile ? 12 : 20,
        },
      ],
    };
  }, [realizedPoints, isMobile]);

  const breakdownColumns: ColumnsType<BreakdownRowRead> = useMemo(
    () => [
      {
        title: DIMENSIONS.find((d) => d.value === dimension)?.label ?? "维度",
        dataIndex: "label",
        key: "label",
        render: (label: string) =>
          dimension === "side" ? SIDE_LABEL[label] ?? label : label,
      },
      {
        title: "平仓次数",
        dataIndex: "trade_count",
        key: "trade_count",
        align: "right",
        sorter: (a, b) => a.trade_count - b.trade_count,
      },
      {
        title: "胜率",
        dataIndex: "win_rate",
        key: "win_rate",
        align: "right",
        sorter: (a, b) => a.win_rate - b.win_rate,
        render: (v: number) => `${(v * 100).toFixed(1)}%`,
      },
      {
        title: "已实现盈亏",
        dataIndex: "realized_pnl_total",
        key: "realized_pnl_total",
        align: "right",
        defaultSortOrder: "descend",
        sorter: (a, b) => a.realized_pnl_total - b.realized_pnl_total,
        render: (v: number) => <PnlText value={v} />,
      },
      {
        title: "单笔均值",
        dataIndex: "avg_pnl",
        key: "avg_pnl",
        align: "right",
        sorter: (a, b) => a.avg_pnl - b.avg_pnl,
        render: (v: number) => <PnlText value={v} />,
      },
    ],
    [dimension]
  );

  const chartOption = useMemo(() => {
    const dates = points.map((p) => p.snapshot_date);
    const equities = points.map((p) => p.total_equity);
    const drawdowns = points.map((p) => p.drawdown_pct * 100);

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
          `<div style="min-width:180px"><strong>${
            params[0]?.axisValueLabel
          }</strong><br/>${params
            .map((p) => {
              if (p.seriesName === "回撤") {
                return `${p.seriesName}: <strong>${p.value.toFixed(2)}%</strong>`;
              }
              return `${p.seriesName}: <strong>${fmtMoney(p.value)} USDT</strong>`;
            })
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
          name: "回撤",
          max: 100,
          nameTextStyle: { color: POSI_PALETTE.textMuted, fontSize: 11 },
          splitLine: { show: false },
          axisLabel: { formatter: (v: number) => `${v.toFixed(0)}%` },
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
          name: "回撤",
          type: "line",
          yAxisIndex: 1,
          smooth: true,
          showSymbol: false,
          data: drawdowns,
          lineStyle: { color: POSI_PALETTE.down, width: 1.5 },
        },
      ],
    };
  }, [points, isMobile]);

  const scopeLabel =
    accountIds.length === 0
      ? `全部账户 (${data?.scope.account_count ?? "—"})`
      : `已选 ${accountIds.length} 个账户`;

  const accountOptions = (accounts.data ?? []).map((a) => ({
    label: a.account_name,
    value: a.id,
  }));

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="交易表现"
        description="基于日快照与平仓事件的 P0 指标，支持单账户或多账户筛选"
      />

      <Card bodyStyle={{ padding: 16 }} style={{ borderRadius: 12 }}>
        <Space
          direction={isMobile ? "vertical" : "horizontal"}
          wrap
          size={12}
          style={{ width: "100%" }}
        >
          <Select
            mode="multiple"
            allowClear
            placeholder="全部账户"
            style={{ minWidth: isMobile ? "100%" : 240 }}
            value={accountIds}
            onChange={(v) => {
              setAccountIds(v);
              setTradePage(1);
            }}
            options={accountOptions}
            maxTagCount={isMobile ? 2 : 4}
          />
          <Segmented
            value={range}
            onChange={(v) => {
              setRange(String(v));
              setTradePage(1);
            }}
            options={RANGES}
          />
          <Space size={8}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              含模拟账户
            </Text>
            <Switch
              size="small"
              checked={includeSimulated}
              onChange={(v) => {
                setIncludeSimulated(v);
                setTradePage(1);
              }}
            />
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            当前范围：{scopeLabel}
          </Text>
        </Space>
      </Card>

      <div>
        <Text
          style={{
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            fontSize: 11,
            color: "var(--posi-text-muted)",
            fontWeight: 500,
          }}
        >
          账户表现（日快照）
        </Text>
        <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label={
                <>
                  区间权益变动
                  <MetricHint
                    title="区间权益变动"
                    text="期末权益减期初权益，基于每日快照汇总"
                  />
                </>
              }
              loading={summary.isLoading}
              value={<PnlText value={data?.equity_change ?? 0} weight={600} />}
              hint={`${((data?.equity_change_pct ?? 0) * 100).toFixed(2)}% · ${fmtMoney(data?.equity_end ?? 0)} USDT`}
              accent={
                (data?.equity_change ?? 0) >= 0 ? "up" : "down"
              }
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label={
                <>
                  最大回撤
                  <MetricHint
                    title="最大回撤"
                    text="权益曲线 peak-to-trough 最大跌幅百分比"
                  />
                </>
              }
              loading={summary.isLoading}
              value={`${((data?.max_drawdown_pct ?? 0) * 100).toFixed(2)}%`}
              hint={`当前回撤 ${((data?.current_drawdown_pct ?? 0) * 100).toFixed(2)}%`}
              accent="down"
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label="期初权益"
              loading={summary.isLoading}
              value={fmtMoney(data?.equity_start ?? 0)}
              hint="USDT"
              accent="neutral"
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label="期末权益"
              loading={summary.isLoading}
              value={fmtMoney(data?.equity_end ?? 0)}
              hint={
                data?.data_coverage.snapshot_days
                  ? `${data.data_coverage.snapshot_days} 天快照`
                  : "暂无快照"
              }
              accent="primary"
            />
          </Col>
        </Row>
      </div>

      <div>
        <Text
          style={{
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            fontSize: 11,
            color: "var(--posi-text-muted)",
            fontWeight: 500,
          }}
        >
          交易表现（平仓事件）
        </Text>
        <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label={
                <>
                  已实现盈亏
                  <MetricHint
                    title="已实现盈亏"
                    text="区间内平仓事件 realized PnL 合计"
                  />
                </>
              }
              loading={summary.isLoading}
              value={
                <PnlText value={data?.realized_pnl_total ?? 0} weight={600} />
              }
              hint={`${data?.trade_count ?? 0} 次平仓`}
              accent={
                (data?.realized_pnl_total ?? 0) >= 0 ? "up" : "down"
              }
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label={
                <>
                  胜率
                  <MetricHint
                    title="胜率"
                    text="盈利平仓次数 / 总平仓次数（持平单独计 breakeven）"
                  />
                </>
              }
              loading={summary.isLoading}
              value={`${((data?.win_rate ?? 0) * 100).toFixed(1)}%`}
              hint={`${data?.win_count ?? 0} 胜 · ${data?.loss_count ?? 0} 负 · ${data?.breakeven_count ?? 0} 平`}
              accent={
                (data?.win_rate ?? 0) >= 0.5 ? "up" : "down"
              }
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label={
                <>
                  Profit Factor
                  <MetricHint
                    title="Profit Factor"
                    text="总盈利 / |总亏损|，无亏损时为 —"
                  />
                </>
              }
              loading={summary.isLoading}
              value={fmtRatio(data?.profit_factor)}
              hint={`盈亏比 ${fmtRatio(data?.win_loss_ratio)}`}
              accent="neutral"
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label="单笔均值"
              loading={summary.isLoading}
              value={<PnlText value={data?.avg_trade_pnl ?? 0} />}
              hint={`最大 ${fmtMoney(data?.largest_win ?? 0)} / 最小 ${fmtMoney(data?.largest_loss ?? 0)}`}
              accent="neutral"
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label={
                <>
                  Calmar 比率
                  <MetricHint
                    title="Calmar 比率"
                    text="年化收益 / 最大回撤。年化基于区间收益按 365 天复利换算，回撤为 0 时为 —"
                  />
                </>
              }
              loading={summary.isLoading}
              value={fmtRatio(data?.calmar_ratio)}
              hint={`年化 ${((data?.annualized_return_pct ?? 0) * 100).toFixed(1)}%`}
              accent="neutral"
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label={
                <>
                  连续盈亏
                  <MetricHint
                    title="连续盈亏"
                    text="按时间顺序的最大连续盈利 / 连续亏损平仓次数"
                  />
                </>
              }
              loading={summary.isLoading}
              value={`${data?.max_win_streak ?? 0} 连胜`}
              hint={`${data?.max_loss_streak ?? 0} 连负`}
              accent={
                (data?.max_win_streak ?? 0) >= (data?.max_loss_streak ?? 0)
                  ? "up"
                  : "down"
              }
            />
          </Col>
        </Row>
      </div>

      <div>
        <Text
          style={{
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            fontSize: 11,
            color: "var(--posi-text-muted)",
            fontWeight: 500,
          }}
        >
          当前敞口
        </Text>
        <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label="未实现盈亏"
              loading={summary.isLoading}
              value={
                <PnlText
                  value={data?.unrealized_pnl ?? 0}
                  suffix="USDT"
                  weight={600}
                />
              }
              hint="USDT"
              accent={
                (data?.unrealized_pnl ?? 0) >= 0 ? "up" : "down"
              }
            />
          </Col>
          <Col xs={12} sm={12} lg={6}>
            <KpiCard
              label="持仓数量"
              loading={summary.isLoading}
              value={data?.open_position_count ?? 0}
              hint="qty &gt; 0"
              accent="neutral"
            />
          </Col>
        </Row>
      </div>

      <Card
        title="权益与回撤"
        extra={
          !isMobile ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              权益来自日快照；回撤为权益峰值回撤百分比
            </Text>
          ) : null
        }
        bodyStyle={{ padding: 16 }}
        style={{ borderRadius: 12 }}
      >
        <AsyncBoundary
          loading={equity.isLoading}
          error={equity.error}
          empty={!points.length}
          emptyText="暂无快照数据，请先同步账户或手动录入"
        >
          <ReactECharts
            theme="posi-light"
            option={chartOption}
            notMerge
            style={{ height: isMobile ? 320 : 420 }}
          />
        </AsyncBoundary>
      </Card>

      <Card
        title="每日已实现盈亏"
        extra={
          !isMobile ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              按平仓事件成交日聚合
            </Text>
          ) : null
        }
        bodyStyle={{ padding: 16 }}
        style={{ borderRadius: 12 }}
      >
        <AsyncBoundary
          loading={realized.isLoading}
          error={realized.error}
          empty={!realizedPoints.length}
          emptyText="区间内暂无平仓记录"
        >
          <ReactECharts
            theme="posi-light"
            option={realizedOption}
            notMerge
            style={{ height: isMobile ? 260 : 320 }}
          />
        </AsyncBoundary>
      </Card>

      <Card
        title="维度分析"
        extra={
          <Segmented
            size="small"
            value={dimension}
            onChange={(v) => setDimension(v as BreakdownDimension)}
            options={DIMENSIONS}
          />
        }
        bodyStyle={{ padding: isMobile ? 8 : 16 }}
        style={{ borderRadius: 12 }}
      >
        <AsyncBoundary
          loading={breakdown.isLoading}
          error={breakdown.error}
          empty={!breakdownRows.length}
          emptyText="区间内暂无平仓记录"
        >
          <Table<BreakdownRowRead>
            rowKey="key"
            size="small"
            columns={breakdownColumns}
            dataSource={breakdownRows}
            pagination={false}
            scroll={{ x: true }}
          />
        </AsyncBoundary>
      </Card>

      <Card
        title="平仓明细"
        extra={
          <Button
            size="small"
            icon={<DownloadOutlined />}
            disabled={!tradeRows.length}
            onClick={onExportTrades}
          >
            导出 CSV
          </Button>
        }
        bodyStyle={{ padding: isMobile ? 8 : 16 }}
        style={{ borderRadius: 12 }}
      >
        <AsyncBoundary
          loading={trades.isLoading}
          error={trades.error}
          empty={!tradeRows.length}
          emptyText="区间内暂无平仓记录"
        >
          <Table<TradeRowRead>
            rowKey="execution_id"
            size="small"
            columns={tradeColumns}
            dataSource={tradeRows}
            onChange={onTradeTableChange}
            pagination={{
              current: trades.data?.page ?? 1,
              pageSize: trades.data?.page_size ?? PAGE_SIZE,
              total: trades.data?.total ?? 0,
              showSizeChanger: false,
            }}
            scroll={{ x: true }}
          />
        </AsyncBoundary>
      </Card>
    </Space>
  );
}
