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
import { useAccounts, usePositions } from "@/api/hooks";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import type { PositionMerged, PositionSplit } from "@/api/types";
import { fmtPrice, fmtQty, fmtRelative } from "@/utils/format";

const { Text } = Typography;

type View = "split" | "merged";

export function PositionsPage() {
  const { isMobile } = useBreakpoint();
  const [view, setView] = useState<View>("split");
  const [keyword, setKeyword] = useState("");
  const accounts = useAccounts();
  const split = usePositions("split");
  const merged = usePositions("merged");

  const accountMap = useMemo(
    () =>
      new Map(
        (accounts.data ?? []).map((a) => [a.id, a.account_name])
      ),
    [accounts.data]
  );

  const filteredSplit = useMemo<PositionSplit[]>(() => {
    const list = split.data ?? [];
    if (!keyword) return list;
    const k = keyword.toUpperCase();
    return list.filter((p) =>
      `${p.canonical_symbol} ${accountMap.get(p.account_id) ?? ""}`
        .toUpperCase()
        .includes(k)
    );
  }, [split.data, keyword, accountMap]);

  const filteredMerged = useMemo<PositionMerged[]>(() => {
    const list = merged.data ?? [];
    if (!keyword) return list;
    const k = keyword.toUpperCase();
    return list.filter((p) => p.canonical_symbol.toUpperCase().includes(k));
  }, [merged.data, keyword]);

  const splitColumns = [
    {
      title: "合约",
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
    {
      title: "方向",
      dataIndex: "side",
      width: 100,
      render: (v: PositionSplit["side"]) => <SideTag side={v} />,
    },
    {
      title: "数量",
      dataIndex: "qty",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    },
    {
      title: "开仓均价",
      dataIndex: "entry_price",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{fmtPrice(v)}</span>,
    },
    {
      title: "标记价",
      dataIndex: "mark_price",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{fmtPrice(v)}</span>,
    },
    {
      title: "未实现盈亏",
      dataIndex: "unrealized_pnl",
      align: "right" as const,
      render: (v: number) => <PnlText value={v} />,
    },
    {
      title: "杠杆",
      dataIndex: "leverage",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{v}x</span>,
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
    {
      title: "更新",
      dataIndex: "updated_at",
      align: "right" as const,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {fmtRelative(v)}
        </Text>
      ),
    },
  ];

  const mergedColumns = [
    {
      title: "合约",
      dataIndex: "canonical_symbol",
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "方向",
      dataIndex: "side",
      width: 100,
      render: (v: PositionMerged["side"]) => <SideTag side={v} />,
    },
    {
      title: "净持仓",
      dataIndex: "qty",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    },
    {
      title: "加权均价",
      dataIndex: "avg_entry_price",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{fmtPrice(v)}</span>,
    },
    {
      title: "标记价",
      dataIndex: "mark_price",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{fmtPrice(v)}</span>,
    },
    {
      title: "名义敞口",
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
  ];

  const isSplit = view === "split";
  const data = isSplit ? filteredSplit : filteredMerged;
  const loading = isSplit ? split.isLoading : merged.isLoading;
  const err = isSplit ? split.error : merged.error;

  // Mobile card view for split positions
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
          <Col>
            <SideTag side={position.side} />
          </Col>
        </Row>

        <Row gutter={[8, 8]}>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              账户
            </Text>
            <div>
              <Text>{accountMap.get(position.account_id) ?? `#${position.account_id}`}</Text>
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
              开仓均价
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(position.entry_price)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              标记价
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
              <PnlText value={position.unrealized_pnl} />
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              杠杆 / 保证金
            </Text>
            <div>
              <span className="posi-numeric">{position.leverage}x</span>
              {position.margin_mode && (
                <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
                  / {position.margin_mode}
                </Text>
              )}
            </div>
          </Col>
          <Col span={24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              更新: {fmtRelative(position.updated_at)}
            </Text>
          </Col>
        </Row>

        <Collapse
          ghost
          size="small"
          items={[
            {
              key: "orders",
              label: "订单详情",
              children: <PositionOrdersTable positionId={position.id} />,
            },
          ]}
        />
      </Space>
    </Card>
  );

  // Mobile card view for merged positions
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
          <Col>
            <SideTag side={position.side} />
          </Col>
        </Row>

        <Row gutter={[8, 8]}>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              净持仓
            </Text>
            <div>
              <span className="posi-numeric">{fmtQty(position.qty)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              加权均价
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(position.avg_entry_price)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              标记价
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(position.mark_price)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              名义敞口
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(Math.abs(position.notional))}</span>
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
              {position.accounts.map((i) => accountMap.get(i) ?? `#${i}`).join(", ")}
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
        description="按账户拆分查看，或按统一 Symbol 合并净敞口"
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
              onClick={() => {
                split.refetch();
                merged.refetch();
              }}
            >
              刷新
            </Button>
          </>
        }
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
          loading={loading}
          error={err}
          empty={!data.length}
          emptyText="暂无持仓"
        >
          <div>
            {isSplit
              ? (data as PositionSplit[]).map(renderSplitCard)
              : (data as PositionMerged[]).map(renderMergedCard)}
          </div>
        </AsyncBoundary>
      ) : (
        <Card bodyStyle={{ padding: 0 }} style={{ borderRadius: 12 }}>
          <AsyncBoundary
            loading={loading}
            error={err}
            empty={!data.length}
            emptyText="暂无持仓"
          >
            <Table
              rowKey={isSplit ? "id" : "canonical_symbol"}
              columns={isSplit ? splitColumns : mergedColumns}
              dataSource={data as never}
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              size="middle"
              expandable={
                isSplit
                  ? {
                      expandedRowRender: (record: PositionSplit) => (
                        <PositionOrdersTable positionId={record.id} />
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
