import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Collapse,
  Input,
  Row,
  Col,
  Segmented,
  Space,
  Tag,
  Table,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { PageHeader } from "@/components/PageHeader";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { PnlText } from "@/components/PnlText";
import { SideTag } from "@/components/SideTag";
import { PositionOrdersTable } from "@/components/PositionOrdersTable";
import RelativeTime from "@/components/RelativeTime";
import {
  useAccounts,
  useLivePositionPrices,
  usePositions,
} from "@/api/hooks";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import type {
  PositionMarket,
  PositionMerged,
  PositionSplit,
} from "@/api/types";
import { fmtPrice, fmtQty } from "@/utils/format";

const { Text } = Typography;

type View = "split" | "merged";

function fmtCostPrice(
  value: number,
  hasCostBasis: boolean | undefined
): string {
  if (hasCostBasis === false || value <= 0) return "—";
  return fmtPrice(value);
}

function fmtSpotUnrealized(
  value: number,
  hasCostBasis: boolean | undefined
): number | null {
  if (hasCostBasis === false) return null;
  return value;
}

export function PositionsPage() {
  const { isMobile } = useBreakpoint();
  const [market, setMarket] = useState<PositionMarket>("derivatives");
  const [view, setView] = useState<View>("split");
  const [keyword, setKeyword] = useState("");
  const accounts = useAccounts();
  const positions = usePositions(view, market);
  const livePrices = useLivePositionPrices(
    view,
    market,
    (positions.data?.length ?? 0) > 0
  );
  const accountsLoading = accounts.isLoading;

  const isSpot = market === "spot";

  const accountMap = useMemo(
    () =>
      new Map(
        (accounts.data ?? []).map((a) => [a.id, a.account_name])
      ),
    [accounts.data]
  );

  const accountById = useMemo(
    () => new Map((accounts.data ?? []).map((a) => [a.id, a])),
    [accounts.data]
  );

  const isCoinPerpPosition = (p: {
    account_id: number;
    account_type?: string | null;
  }) =>
    p.account_type === "coin_perp" ||
    accountById.get(p.account_id)?.account_type === "coin_perp";

  const pnlAssetFor = (p: PositionSplit) =>
    p.pnl_asset ?? p.canonical_symbol.split("-")[0];

  const orderTableProps = (p: PositionSplit) => ({
    isCoinMargined: isCoinPerpPosition(p),
    pnlAsset: isCoinPerpPosition(p) ? pnlAssetFor(p) : null,
    isSpot,
  });

  const livePriceMap = useMemo(() => {
    const map = new Map<number | string, number>();
    for (const item of livePrices.data?.prices ?? []) {
      const key = view === "split" ? item.position_id : item.canonical_symbol;
      if (key !== null && key !== undefined) {
        map.set(key, item.price);
      }
    }
    return map;
  }, [livePrices.data?.prices, view]);

  const displayData = useMemo(() => {
    if (!positions.data) return [];
    if (view === "split") {
      return (positions.data as PositionSplit[]).map((position) => {
        const price = livePriceMap.get(position.id);
        return price === undefined ? position : { ...position, mark_price: price };
      });
    }
    return (positions.data as PositionMerged[]).map((position) => {
      const price = livePriceMap.get(position.canonical_symbol);
      if (price === undefined) return position;
      return {
        ...position,
        mark_price: price,
        notional:
          position.side === "short"
            ? -Math.abs(position.qty * price)
            : Math.abs(position.qty * price),
      };
    });
  }, [livePriceMap, positions.data, view]);

  const filteredData = useMemo(() => {
    const list = displayData;
    const k = keyword.toUpperCase();
    if (view === "split") {
      const rows = (list as PositionSplit[]).filter(
        (p) =>
          !k ||
          `${p.canonical_symbol} ${accountMap.get(p.account_id) ?? ""}`
            .toUpperCase()
            .includes(k)
      );
      // Stable ordering: symbol, then account name, so multi-account lists
      // don't reshuffle on every refetch.
      return [...rows].sort((a, b) => {
        const sym = a.canonical_symbol.localeCompare(b.canonical_symbol);
        if (sym !== 0) return sym;
        const an = accountMap.get(a.account_id) ?? `#${a.account_id}`;
        const bn = accountMap.get(b.account_id) ?? `#${b.account_id}`;
        return an.localeCompare(bn);
      });
    }
    // Merged view is already sorted/filtered server-side; only apply search.
    return (list as PositionMerged[]).filter(
      (p) => !k || p.canonical_symbol.toUpperCase().includes(k)
    );
  }, [displayData, keyword, accountMap, view]);

  const splitColumns = useMemo<ColumnsType<PositionSplit>>(
    () => [
      {
        title: isSpot ? "交易对" : "合约",
        dataIndex: "canonical_symbol",
        render: (v: string) => <Text strong>{v}</Text>,
      },
      {
        title: "账户",
        dataIndex: "account_id",
        render: (v: number) => (
          <Text type="secondary">
            {accountMap.get(v) ?? (accountsLoading ? "…" : `#${v}`)}
          </Text>
        ),
      },
      ...(!isSpot
        ? [
            {
              title: "方向",
              dataIndex: "side",
              width: 100,
              render: (v: PositionSplit["side"]) => <SideTag side={v} />,
            },
          ]
        : []),
      {
        title: "数量",
        dataIndex: "qty",
        align: "right" as const,
        render: (v: number) => (
          <span className="posi-numeric">{fmtQty(v)}</span>
        ),
      },
      {
        title: isSpot ? "成本价" : "开仓均价",
        dataIndex: "entry_price",
        align: "right" as const,
        render: (v: number, record: PositionSplit) => (
          <span className="posi-numeric">
            {fmtCostPrice(v, record.has_cost_basis)}
          </span>
        ),
      },
      {
        title: isSpot ? "现价" : "标记价",
        dataIndex: "mark_price",
        align: "right" as const,
        render: (v: number) => (
          <span className="posi-numeric">{fmtPrice(v)}</span>
        ),
      },
      {
        title: "未实现盈亏",
        dataIndex: "unrealized_pnl",
        align: "right" as const,
        render: (v: number, record: PositionSplit) => {
          const pnl = fmtSpotUnrealized(v, record.has_cost_basis);
          if (pnl === null) {
            return (
              <Text type="secondary" style={{ fontSize: 12 }}>
                —
              </Text>
            );
          }
          return (
            <PnlText
              value={pnl}
              suffix="USDT"
            />
          );
        },
      },
      {
        title: "已实现盈亏",
        dataIndex: "realized_pnl",
        align: "right" as const,
        render: (v: number) => (
          <PnlText
            value={v}
            suffix="USDT"
          />
        ),
      },
      ...(!isSpot
        ? [
            {
              title: "杠杆",
              dataIndex: "leverage",
              align: "right" as const,
              render: (v: number) => (
                <span className="posi-numeric">{v}x</span>
              ),
            },
            {
              title: "保证金模式",
              dataIndex: "margin_mode",
              align: "right" as const,
              render: (v: string | null) => (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {v ?? "—"}
                </Text>
              ),
            },
          ]
        : []),
      {
        title: "更新",
        dataIndex: "updated_at",
        align: "right" as const,
        render: (v: string) => (
          <RelativeTime value={v} style={{ fontSize: 12 }} />
        ),
      },
    ],
    [accountMap, isSpot, accountsLoading]
  );

  const mergedColumns = useMemo<ColumnsType<PositionMerged>>(
    () => [
      {
        title: isSpot ? "交易对" : "合约",
        dataIndex: "canonical_symbol",
        render: (v: string) => <Text strong>{v}</Text>,
      },
      ...(!isSpot
        ? [
            {
              title: "方向",
              dataIndex: "side",
              width: 100,
              render: (v: PositionMerged["side"]) => <SideTag side={v} />,
            },
          ]
        : []),
      {
        title: isSpot ? "总持仓" : "净持仓",
        dataIndex: "qty",
        align: "right" as const,
        render: (v: number) => (
          <span className="posi-numeric">{fmtQty(v)}</span>
        ),
      },
      {
        title: isSpot ? "加权成本" : "加权均价",
        dataIndex: "avg_entry_price",
        align: "right" as const,
        render: (v: number) => (
          <span className="posi-numeric">
            {v > 0 ? fmtPrice(v) : "—"}
          </span>
        ),
      },
      {
        title: isSpot ? "现价" : "标记价",
        dataIndex: "mark_price",
        align: "right" as const,
        render: (v: number) => (
          <span className="posi-numeric">{fmtPrice(v)}</span>
        ),
      },
      {
        title: isSpot ? "总市值" : "名义敞口",
        dataIndex: "notional",
        align: "right" as const,
        render: (v: number) => (
          <span className="posi-numeric">{fmtPrice(Math.abs(v))}</span>
        ),
      },
      {
        title: "未实现盈亏",
        dataIndex: "unrealized_pnl",
        align: "right" as const,
        render: (v: number) => <PnlText value={v} />,
      },
      {
        title: "已实现盈亏",
        dataIndex: "realized_pnl",
        align: "right" as const,
        render: (v: number) => <PnlText value={v} />,
      },
      {
        title: "账户分布",
        dataIndex: "accounts",
        align: "right" as const,
        render: (ids: number[]) => (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {ids.length} 账户 ·{" "}
            {ids.map((i) => accountMap.get(i) ?? `#${i}`).join(", ")}
          </Text>
        ),
      },
    ],
    [accountMap, isSpot]
  );

  const isSplit = view === "split";
  const emptyText = isSpot
    ? "暂无现货持仓，请确认已添加现货账户并完成同步"
    : "暂无合约持仓";

  const renderSplitCard = (position: PositionSplit) => (
    <Card
      key={position.id}
      size="small"
      style={{ marginBottom: 12 }}
      bodyStyle={{ padding: 12 }}
    >
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Text strong style={{ fontSize: 16 }}>
              {position.canonical_symbol}
            </Text>
          </Col>
          {!isSpot && (
            <Col>
              <SideTag side={position.side} />
            </Col>
          )}
        </Row>

        <Row gutter={[8, 8]}>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              账户
            </Text>
            <div>
              <Text>
                {accountMap.get(position.account_id) ??
                  `#${position.account_id}`}
              </Text>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              数量
            </Text>
            <div>
              <span className="posi-numeric">{fmtQty(position.qty)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isSpot ? "成本价" : "开仓均价"}
            </Text>
            <div>
              <span className="posi-numeric">
                {fmtCostPrice(position.entry_price, position.has_cost_basis)}
              </span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isSpot ? "现价" : "标记价"}
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(position.mark_price)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              未实现盈亏
            </Text>
            <div>
              {fmtSpotUnrealized(
                position.unrealized_pnl,
                position.has_cost_basis
              ) === null ? (
                <Text type="secondary">—</Text>
              ) : (
                <PnlText
                  value={position.unrealized_pnl}
                  suffix="USDT"
                />
              )}
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              已实现盈亏
            </Text>
            <div>
              <PnlText
                value={position.realized_pnl}
                suffix="USDT"
              />
            </div>
          </Col>
          {!isSpot && (
            <Col span={12}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                杠杆 / 模式
              </Text>
              <div>
                <span className="posi-numeric">{position.leverage}x</span>
                {position.margin_mode && (
                  <Text
                    type="secondary"
                    style={{ fontSize: 12, marginLeft: 4 }}
                  >
                    / {position.margin_mode}
                  </Text>
                )}
              </div>
            </Col>
          )}
          <Col span={24}>
            <span style={{ fontSize: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                更新:{" "}
              </Text>
              <RelativeTime
                value={position.updated_at}
                style={{ fontSize: 12 }}
              />
            </span>
          </Col>
        </Row>

        <Collapse
          ghost
          size="small"
          destroyInactivePanel
          items={[
            {
              key: "orders",
              label: isSpot ? "买入批次" : "订单详情",
              children: (
                <PositionOrdersTable
                  positionId={position.id}
                  {...orderTableProps(position)}
                />
              ),
            },
          ]}
        />
      </Space>
    </Card>
  );

  const renderMergedCard = (position: PositionMerged) => (
    <Card
      key={position.canonical_symbol}
      size="small"
      style={{ marginBottom: 12 }}
      bodyStyle={{ padding: 12 }}
    >
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Text strong style={{ fontSize: 16 }}>
              {position.canonical_symbol}
            </Text>
          </Col>
          {!isSpot && (
            <Col>
              <SideTag side={position.side} />
            </Col>
          )}
        </Row>

        <Row gutter={[8, 8]}>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isSpot ? "总持仓" : "净持仓"}
            </Text>
            <div>
              <span className="posi-numeric">{fmtQty(position.qty)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isSpot ? "加权成本" : "加权均价"}
            </Text>
            <div>
              <span className="posi-numeric">
                {position.avg_entry_price > 0
                  ? fmtPrice(position.avg_entry_price)
                  : "—"}
              </span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isSpot ? "现价" : "标记价"}
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(position.mark_price)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isSpot ? "总市值" : "名义敞口"}
            </Text>
            <div>
              <span className="posi-numeric">
                {fmtPrice(Math.abs(position.notional))}
              </span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              未实现盈亏
            </Text>
            <div>
              <PnlText value={position.unrealized_pnl} suffix="USDT" />
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              已实现盈亏
            </Text>
            <div>
              <PnlText value={position.realized_pnl} suffix="USDT" />
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              账户分布
            </Text>
            <div>
              <Text style={{ fontSize: 12 }}>
                {position.accounts.length} 账户
              </Text>
            </div>
          </Col>
          <Col span={24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {position.accounts
                .map((i) => accountMap.get(i) ?? `#${i}`)
                .join(", ")}
            </Text>
          </Col>
        </Row>
      </Space>
    </Card>
  );

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="仓位"
        description={
          isSpot
            ? "查看现货账户持仓，支持按账户拆分或跨账户合并"
            : "按账户拆分查看合约仓位，或按统一 Symbol 合并净敞口"
        }
        extra={
          <>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索 Symbol / 账户"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              style={{ width: isMobile ? "100%" : 240, maxWidth: "100%" }}
            />
            <Button
              icon={<ReloadOutlined />}
              loading={positions.isFetching}
              onClick={() => {
                void positions.refetch();
                void livePrices.refetch();
              }}
            >
              刷新
            </Button>
            <Tag
              color={
                livePrices.isError
                  ? "error"
                  : (livePrices.data?.failed_exchanges.length ?? 0) > 0
                    ? "warning"
                  : livePrices.isFetching
                    ? "processing"
                    : "success"
              }
            >
              {livePrices.isError
                ? "行情更新失败，保留当前价格"
                : (livePrices.data?.failed_exchanges.length ?? 0) > 0
                  ? "部分交易所行情失败，保留当前价格"
                : livePrices.isFetching
                  ? "行情更新中"
                  : "行情自动更新 · 15 秒"}
            </Tag>
          </>
        }
      />

      <Segmented
        block={isMobile}
        value={market}
        onChange={(v) => setMarket(v as PositionMarket)}
        options={[
          { label: "合约", value: "derivatives" },
          { label: "现货", value: "spot" },
        ]}
      />

      <Segmented
        block={isMobile}
        value={view}
        onChange={(v) => setView(v as View)}
        options={[
          { label: "分仓视图", value: "split" },
          { label: "合仓视图", value: "merged" },
        ]}
      />

      {isMobile ? (
        <AsyncBoundary
          loading={positions.isLoading}
          error={positions.error}
          empty={!filteredData.length}
          emptyText={emptyText}
        >
          <div>
            {isSplit
              ? (filteredData as PositionSplit[]).map(renderSplitCard)
              : (filteredData as PositionMerged[]).map(renderMergedCard)}
          </div>
        </AsyncBoundary>
      ) : (
        <Card bodyStyle={{ padding: 0 }} style={{ borderRadius: 12 }}>
          <AsyncBoundary
            loading={positions.isLoading}
            error={positions.error}
            empty={!filteredData.length}
            emptyText={emptyText}
          >
            {isSplit ? (
              <Table<PositionSplit>
                rowKey="id"
                columns={splitColumns}
                dataSource={filteredData as PositionSplit[]}
                loading={positions.isFetching && !positions.isLoading}
                pagination={{ pageSize: 20, hideOnSinglePage: true }}
                size="middle"
                expandable={{
                  expandedRowRender: (record) => (
                    <PositionOrdersTable
                      positionId={record.id}
                      {...orderTableProps(record)}
                    />
                  ),
                  rowExpandable: () => true,
                }}
              />
            ) : (
              <Table<PositionMerged>
                rowKey="canonical_symbol"
                columns={mergedColumns}
                dataSource={filteredData as PositionMerged[]}
                loading={positions.isFetching && !positions.isLoading}
                pagination={{ pageSize: 20, hideOnSinglePage: true }}
                size="middle"
              />
            )}
          </AsyncBoundary>
        </Card>
      )}
    </Space>
  );
}
