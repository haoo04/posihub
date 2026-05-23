import { useState } from "react";
import {
  Button,
  Card,
  Col,
  Modal,
  Row,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  ScissorOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { OrderMarginDisplay, OrderPnlDisplay } from "./OrderPnlDisplay";
import RelativeTime from "./RelativeTime";
import { useDeletePositionOrder, usePositionOrders } from "@/api/hooks";
import type { PositionOrderWithPnL } from "@/api/types";
import { fmtPrice, fmtQty } from "@/utils/format";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { PositionOrderModal } from "./PositionOrderModal";
import { PositionCloseFifoModal } from "./PositionCloseFifoModal";
import { PositionCloseSpecifiedModal } from "./PositionCloseSpecifiedModal";

const { Text } = Typography;
const { confirm } = Modal;

interface PositionOrdersTableProps {
  positionId: number;
  isCoinMargined?: boolean;
  pnlAsset?: string | null;
}

function renderPriceCell(record: PositionOrderWithPnL) {
  const closePx = record.close_price;

  if (record.status === "open") {
    return (
      <span className="posi-numeric">{fmtPrice(record.mark_price)}</span>
    );
  }

  if (record.status === "closed") {
    return (
      <span className="posi-numeric">
        {closePx != null ? fmtPrice(closePx) : "—"}
      </span>
    );
  }

  return (
    <Space direction="vertical" size={0} style={{ textAlign: "right" }}>
      <Text type="secondary" style={{ fontSize: 11 }}>
        平仓 {closePx != null ? fmtPrice(closePx) : "—"}
      </Text>
      <span className="posi-numeric">{fmtPrice(record.mark_price)}</span>
    </Space>
  );
}

function sourceTag(source: string) {
  const colorMap: Record<string, string> = {
    api: "blue",
    manual: "orange",
    simulated: "purple",
  };
  return (
    <Tag color={colorMap[source] || "default"}>{source.toUpperCase()}</Tag>
  );
}

function statusTag(status: string) {
  const colorMap: Record<string, string> = {
    open: "green",
    partial: "orange",
    closed: "default",
  };
  const textMap: Record<string, string> = {
    open: "持仓中",
    partial: "部分平仓",
    closed: "已平仓",
  };
  return <Tag color={colorMap[status]}>{textMap[status] || status}</Tag>;
}

export function PositionOrdersTable({
  positionId,
  isCoinMargined = false,
  pnlAsset = null,
}: PositionOrdersTableProps) {
  const { isMobile } = useBreakpoint();
  const { data: orders, isLoading, error } = usePositionOrders(positionId);
  const deleteMutation = useDeletePositionOrder();
  const [editingOrder, setEditingOrder] = useState<PositionOrderWithPnL | null>(
    null
  );
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [isSpecifiedCloseModalOpen, setIsSpecifiedCloseModalOpen] =
    useState(false);

  const defaultClosePrice = orders?.[0]?.mark_price;
  const hasOpenQty = (orders ?? []).some((o) => o.remaining_qty > 0);

  const handleDelete = (orderId: number) => {
    confirm({
      title: "确认删除",
      icon: <ExclamationCircleOutlined />,
      content: "确定要删除这个订单吗？此操作不可撤销。",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        try {
          await deleteMutation.mutateAsync(orderId);
          message.success("订单已删除");
        } catch (err) {
          message.error("删除失败");
        }
      },
    });
  };

  const columns = [
    {
      title: "订单ID",
      dataIndex: "id",
      width: 80,
      render: (v: number) => <Text type="secondary">#{v}</Text>,
    },
    {
      title: "来源",
      dataIndex: "source",
      width: 80,
      render: (v: string) => sourceTag(v),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (v: string) => statusTag(v),
    },
    {
      title: "开仓数量",
      dataIndex: "open_qty",
      align: "right" as const,
      width: 100,
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    },
    {
      title: "剩余数量",
      dataIndex: "remaining_qty",
      align: "right" as const,
      width: 100,
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    },
    {
      title: "开仓价",
      dataIndex: "entry_price",
      align: "right" as const,
      width: 120,
      render: (v: number) => (
        <span className="posi-numeric">{fmtPrice(v)}</span>
      ),
    },
    {
      title: "价格",
      key: "price",
      align: "right" as const,
      width: 130,
      render: (_: unknown, record: PositionOrderWithPnL) => renderPriceCell(record),
    },
    {
      title: "未实现盈亏",
      dataIndex: "unrealized_pnl",
      align: "right" as const,
      width: 150,
      render: (_: number, record: PositionOrderWithPnL) => {
        const upnl = record.unrealized_pnl_usdt ?? record.unrealized_pnl;
        return (
          <Space direction="vertical" size={0} style={{ textAlign: "right" }}>
            <OrderPnlDisplay
              nativeValue={record.unrealized_pnl_native}
              usdtValue={upnl}
              asset={record.pnl_asset ?? pnlAsset}
              coinMargined={isCoinMargined}
            />
            <Text
              type="secondary"
              style={{ fontSize: 11 }}
              className={upnl >= 0 ? "posi-positive" : "posi-negative"}
            >
              {upnl >= 0 ? "+" : ""}
              {record.unrealized_pnl_pct.toFixed(2)}%
            </Text>
          </Space>
        );
      },
    },
    {
      title: "已实现盈亏",
      dataIndex: "realized_pnl",
      align: "right" as const,
      width: 140,
      render: (_: number, record: PositionOrderWithPnL) => (
        <OrderPnlDisplay
          nativeValue={record.realized_pnl_native}
          usdtValue={record.realized_pnl_usdt ?? record.realized_pnl}
          asset={record.pnl_asset ?? pnlAsset}
          coinMargined={isCoinMargined}
        />
      ),
    },
    {
      title: "杠杆",
      dataIndex: "leverage",
      align: "right" as const,
      width: 80,
      render: (v: number) => <span className="posi-numeric">{v}x</span>,
    },
    {
      title: "保证金",
      dataIndex: "margin",
      align: "right" as const,
      width: 120,
      render: (v: number | null) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          <OrderMarginDisplay
            value={v}
            asset={pnlAsset}
            coinMargined={isCoinMargined}
          />
        </Text>
      ),
    },
    {
      title: "MMR",
      dataIndex: "mmr",
      align: "right" as const,
      width: 80,
      render: (v: number | null) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {v !== null ? `${(v * 100).toFixed(2)}%` : "—"}
        </Text>
      ),
    },
    {
      title: "强平价",
      dataIndex: "liquidation_price",
      align: "right" as const,
      width: 120,
      render: (v: number | null) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {v !== null ? fmtPrice(v) : "—"}
        </Text>
      ),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      align: "right" as const,
      width: 100,
      render: (v: string) => (
        <RelativeTime value={v} style={{ fontSize: 12 }} />
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 120,
      fixed: "right" as const,
      render: (_: unknown, record: PositionOrderWithPnL) => (
        <Space size="small">
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => setEditingOrder(record)}
          >
            编辑
          </Button>
          <Button
            type="text"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  if (error) {
    return (
      <div style={{ padding: 16, color: "#ff4d4f" }}>
        加载订单失败: {error.message}
      </div>
    );
  }

  const list = orders ?? [];

  const renderMobileOrderCard = (order: PositionOrderWithPnL) => (
    <Card
      key={order.id}
      size="small"
      style={{ marginBottom: 0 }}
      bodyStyle={{ padding: 12 }}
    >
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        <Row justify="space-between" align="middle" gutter={8}>
          <Col flex="auto">
            <Text type="secondary" style={{ fontSize: 12 }}>
              订单 #{order.id}
            </Text>
          </Col>
          <Col>
            <Space size={4} wrap>
              {sourceTag(order.source)}
              {statusTag(order.status)}
            </Space>
          </Col>
        </Row>

        <Row gutter={[8, 8]}>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              开仓数量
            </Text>
            <div>
              <span className="posi-numeric">{fmtQty(order.open_qty)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              剩余数量
            </Text>
            <div>
              <span className="posi-numeric">{fmtQty(order.remaining_qty)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              开仓价
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(order.entry_price)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {order.status === "closed"
                ? "平仓价"
                : order.status === "partial"
                  ? "平仓 / 当前"
                  : "当前价"}
            </Text>
            <div>{renderPriceCell(order)}</div>
          </Col>
          <Col span={24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              未实现盈亏
            </Text>
            <div>
              <OrderPnlDisplay
                nativeValue={order.unrealized_pnl_native}
                usdtValue={order.unrealized_pnl_usdt ?? order.unrealized_pnl}
                asset={order.pnl_asset ?? pnlAsset}
                coinMargined={isCoinMargined}
              />
              <Text
                type="secondary"
                style={{ fontSize: 11, marginLeft: 8 }}
                className={
                  (order.unrealized_pnl_usdt ?? order.unrealized_pnl) >= 0
                    ? "posi-positive"
                    : "posi-negative"
                }
              >
                {(order.unrealized_pnl_usdt ?? order.unrealized_pnl) >= 0
                  ? "+"
                  : ""}
                {order.unrealized_pnl_pct.toFixed(2)}%
              </Text>
            </div>
          </Col>
          <Col span={24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              已实现盈亏
            </Text>
            <div>
              <OrderPnlDisplay
                nativeValue={order.realized_pnl_native}
                usdtValue={order.realized_pnl_usdt ?? order.realized_pnl}
                asset={order.pnl_asset ?? pnlAsset}
                coinMargined={isCoinMargined}
              />
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              杠杆
            </Text>
            <div>
              <span className="posi-numeric">{order.leverage}x</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              保证金
            </Text>
            <div>
              <OrderMarginDisplay
                value={order.margin}
                asset={pnlAsset}
                coinMargined={isCoinMargined}
              />
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              MMR
            </Text>
            <div>
              <Text type="secondary" style={{ fontSize: 13 }}>
                {order.mmr !== null ? `${(order.mmr * 100).toFixed(2)}%` : "—"}
              </Text>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              强平价
            </Text>
            <div>
              <Text type="secondary" style={{ fontSize: 13 }}>
                {order.liquidation_price !== null
                  ? fmtPrice(order.liquidation_price)
                  : "—"}
              </Text>
            </div>
          </Col>
          <Col span={24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              创建
            </Text>
            <div>
              <RelativeTime value={order.created_at} style={{ fontSize: 12 }} />
            </div>
          </Col>
        </Row>

        <Space size="small" style={{ width: "100%", justifyContent: "flex-end" }}>
          <Button
            type="default"
            size="small"
            icon={<EditOutlined />}
            onClick={() => setEditingOrder(order)}
          >
            编辑
          </Button>
          <Button
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(order.id)}
          >
            删除
          </Button>
        </Space>
      </Space>
    </Card>
  );

  return (
    <div style={{ padding: isMobile ? "0 0 12px" : "0 16px 16px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <Text strong>订单明细</Text>
        <Space size="small" wrap>
          <Button
            size="small"
            icon={<ScissorOutlined />}
            onClick={() => setIsCloseModalOpen(true)}
            disabled={!hasOpenQty}
          >
            FIFO 平仓
          </Button>
          <Button
            size="small"
            icon={<SwapOutlined />}
            onClick={() => setIsSpecifiedCloseModalOpen(true)}
            disabled={!hasOpenQty}
          >
            指定配对
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            添加订单
          </Button>
        </Space>
      </div>

      {isMobile ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {isLoading ? (
            <Text type="secondary">加载中…</Text>
          ) : list.length === 0 ? (
            <Text type="secondary">暂无订单数据</Text>
          ) : (
            list.map(renderMobileOrderCard)
          )}
        </div>
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={list}
          loading={isLoading}
          pagination={false}
          size="small"
          scroll={{ x: 1520 }}
          locale={{ emptyText: "暂无订单数据" }}
        />
      )}

      <PositionOrderModal
        open={isCreateModalOpen}
        positionId={positionId}
        marginAsset={isCoinMargined ? pnlAsset : null}
        onCancel={() => setIsCreateModalOpen(false)}
        onSuccess={() => setIsCreateModalOpen(false)}
      />

      <PositionOrderModal
        open={!!editingOrder}
        positionId={positionId}
        order={editingOrder || undefined}
        marginAsset={isCoinMargined ? pnlAsset : null}
        onCancel={() => setEditingOrder(null)}
        onSuccess={() => setEditingOrder(null)}
      />

      <PositionCloseFifoModal
        open={isCloseModalOpen}
        positionId={positionId}
        defaultClosePrice={defaultClosePrice}
        onCancel={() => setIsCloseModalOpen(false)}
        onSuccess={() => setIsCloseModalOpen(false)}
      />

      <PositionCloseSpecifiedModal
        open={isSpecifiedCloseModalOpen}
        positionId={positionId}
        defaultClosePrice={defaultClosePrice}
        onCancel={() => setIsSpecifiedCloseModalOpen(false)}
        onSuccess={() => setIsSpecifiedCloseModalOpen(false)}
      />
    </div>
  );
}
