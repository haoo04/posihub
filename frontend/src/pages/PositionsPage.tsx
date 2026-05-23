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
  Table,
  Typography,
} from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { PageHeader } from "@/components/PageHeader";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { PnlText } from "@/components/PnlText";
import { SideTag } from "@/components/SideTag";
import { PositionOrdersTable } from "@/components/PositionOrdersTable";
import RelativeTime from "@/components/RelativeTime";
import { useAccounts, usePositions } from "@/api/hooks";
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

  const filteredData = useMemo(() => {
    const list = positions.data ?? [];
    if (!keyword) return list;
    const k = keyword.toUpperCase();
    if (view === "split") {
      return (list as PositionSplit[]).filter((p) =>
        `${p.canonical_symbol} ${accountMap.get(p.account_id) ?? ""}`
          .toUpperCase()
          .includes(k)
      );
    }
    return (list as PositionMerged[]).filter((p) =>
      p.canonical_symbol.toUpperCase().includes(k)
    );
  }, [positions.data, keyword, accountMap, view]);

  const splitColumns = useMemo(
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
          <Text type="secondary">{accountMap.get(v) ?? `#${v}`}</Text>
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
              suffix={isCoinPerpPosition(record) ? "USDT" : undefined}
            />
          );
        },
      },
      {
        title: "已实现盈亏",
        dataIndex: "realized_pnl",
        align: "right" as const,
        render: (v: number, record: PositionSplit) => (
          <PnlText
            value={v}
            suffix={isCoinPerpPosition(record) ? "USDT" : undefined}
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
              title: "保证金",
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
    [accountMap, isSpot]
  );

  const mergedColumns = useMemo(
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
  const columns = isSplit ? splitColumns : mergedColumns;
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
                  suffix={isCoinPerpPosition(position) ? "USDT" : undefined}
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
                suffix={isCoinPerpPosition(position) ? "USDT" : undefined}
              />
            </div>
          </Col>
          {!isSpot && (
            <Col span={12}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                杠杆 / 保证金
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
              <PnlText value={position.unrealized_pnl} />
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              已实现盈亏
            </Text>
            <div>
              <PnlText value={position.realized_pnl} />
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
              onClick={() => positions.refetch()}
            >
              刷新
            </Button>
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
            <Table
              rowKey={isSplit ? "id" : "canonical_symbol"}
              columns={columns as never}
              dataSource={filteredData as never}
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              size="middle"
              expandable={
                isSplit
                  ? {
                      expandedRowRender: (record: PositionSplit) => (
                        <PositionOrdersTable
                          positionId={record.id}
                          {...orderTableProps(record)}
                        />
                      ),
                      rowExpandable: () => true,
                    }
                  : undefined
              }
            />
          </AsyncBoundary>
        </Card>
      )}
    </Space>
  );
}
