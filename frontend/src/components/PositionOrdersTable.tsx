import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType, TableProps } from "antd/es/table";
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
import {
  ACTIVE_DEFAULT_SORT,
  HISTORY_DEFAULT_SORT,
  antSortOrder,
  partitionOrders,
  sortFromAnt,
  sortOrders,
  type OrderSortField,
  type OrderSortState,
} from "@/utils/positionOrders";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { PositionOrderModal } from "./PositionOrderModal";
import { PositionCloseFifoModal } from "./PositionCloseFifoModal";
import { PositionCloseSpecifiedModal } from "./PositionCloseSpecifiedModal";

const { Text } = Typography;
const { confirm } = Modal;

type OrderSectionVariant = "active" | "history";

interface PositionOrdersTableProps {
  positionId: number;
  isCoinMargined?: boolean;
  pnlAsset?: string | null;
  isSpot?: boolean;
}

const ACTIVE_MOBILE_SORT_OPTIONS = [
  { label: "创建时间 ↑", value: "created_at:asc" },
  { label: "创建时间 ↓", value: "created_at:desc" },
  { label: "开仓价 ↑", value: "entry_price:asc" },
  { label: "开仓价 ↓", value: "entry_price:desc" },
  { label: "数量 ↑", value: "open_qty:asc" },
  { label: "数量 ↓", value: "open_qty:desc" },
  { label: "未实现盈亏 ↑", value: "unrealized_pnl:asc" },
  { label: "未实现盈亏 ↓", value: "unrealized_pnl:desc" },
  { label: "已实现盈亏 ↑", value: "realized_pnl:asc" },
  { label: "已实现盈亏 ↓", value: "realized_pnl:desc" },
] as const;

const HISTORY_MOBILE_SORT_OPTIONS = [
  { label: "平仓时间 ↓", value: "updated_at:desc" },
  { label: "平仓时间 ↑", value: "updated_at:asc" },
  { label: "创建时间 ↓", value: "created_at:desc" },
  { label: "创建时间 ↑", value: "created_at:asc" },
  { label: "已实现盈亏 ↓", value: "realized_pnl:desc" },
  { label: "已实现盈亏 ↑", value: "realized_pnl:asc" },
  { label: "平仓价 ↓", value: "close_price:desc" },
  { label: "平仓价 ↑", value: "close_price:asc" },
] as const;

function parseMobileSortValue(value: string): OrderSortState {
  const [field, order] = value.split(":") as [OrderSortField, "asc" | "desc"];
  return { field, order };
}

function mobileSortValue(sort: OrderSortState): string {
  return `${sort.field}:${sort.order}`;
}

function renderActivePriceCell(record: PositionOrderWithPnL) {
  const closePx = record.close_price;

  if (record.status === "open") {
    return (
      <span className="posi-numeric">{fmtPrice(record.mark_price)}</span>
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

function renderHistoryPriceCell(record: PositionOrderWithPnL) {
  const closePx = record.close_price;
  return (
    <span className="posi-numeric">
      {closePx != null ? fmtPrice(closePx) : "—"}
    </span>
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

interface BuildColumnsOptions {
  variant: OrderSectionVariant;
  isSpot: boolean;
  isCoinMargined: boolean;
  pnlAsset: string | null;
  sort: OrderSortState;
  onEdit: (order: PositionOrderWithPnL) => void;
  onDelete: (orderId: number, isHistory: boolean) => void;
}

function numericSorter(field: OrderSortField) {
  return (a: PositionOrderWithPnL, b: PositionOrderWithPnL) => {
    if (field === "unrealized_pnl") {
      return (
        (a.unrealized_pnl_usdt ?? a.unrealized_pnl) -
        (b.unrealized_pnl_usdt ?? b.unrealized_pnl)
      );
    }
    if (field === "realized_pnl") {
      return (
        (a.realized_pnl_usdt ?? a.realized_pnl) -
        (b.realized_pnl_usdt ?? b.realized_pnl)
      );
    }
    if (field === "close_price") {
      return (a.close_price ?? 0) - (b.close_price ?? 0);
    }
    if (field === "created_at" || field === "updated_at") {
      return new Date(a[field]).getTime() - new Date(b[field]).getTime();
    }
    return (a[field as keyof PositionOrderWithPnL] as number) -
      (b[field as keyof PositionOrderWithPnL] as number);
  };
}

function buildColumns({
  variant,
  isSpot,
  isCoinMargined,
  pnlAsset,
  sort,
  onEdit,
  onDelete,
}: BuildColumnsOptions): ColumnsType<PositionOrderWithPnL> {
  const isHistory = variant === "history";
  const sortOrderFor = (field: OrderSortField) =>
    sort.field === field ? antSortOrder(sort) : null;

  const cols: ColumnsType<PositionOrderWithPnL> = [
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
      title: isSpot ? "买入数量" : "开仓数量",
      dataIndex: "open_qty",
      align: "right",
      width: 100,
      sorter: numericSorter("open_qty"),
      sortOrder: sortOrderFor("open_qty"),
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    },
  ];

  if (!isHistory) {
    cols.push({
      title: "剩余数量",
      dataIndex: "remaining_qty",
      align: "right",
      width: 100,
      sorter: numericSorter("remaining_qty"),
      sortOrder: sortOrderFor("remaining_qty"),
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    });
  }

  cols.push(
    {
      title: isSpot ? "买入价" : "开仓价",
      dataIndex: "entry_price",
      align: "right",
      width: 120,
      sorter: numericSorter("entry_price"),
      sortOrder: sortOrderFor("entry_price"),
      render: (v: number) => (
        <span className="posi-numeric">{fmtPrice(v)}</span>
      ),
    },
    {
      title: isHistory ? (isSpot ? "卖出价" : "平仓价") : "价格",
      key: "price",
      align: "right",
      width: 130,
      ...(isHistory
        ? {
            sorter: numericSorter("close_price"),
            sortOrder: sortOrderFor("close_price"),
          }
        : {}),
      render: (_: unknown, record: PositionOrderWithPnL) =>
        isHistory
          ? renderHistoryPriceCell(record)
          : renderActivePriceCell(record),
    }
  );

  if (!isHistory) {
    cols.push({
      title: "未实现盈亏",
      dataIndex: "unrealized_pnl",
      align: "right",
      width: 150,
      sorter: numericSorter("unrealized_pnl"),
      sortOrder: sortOrderFor("unrealized_pnl"),
      render: (_: number, record: PositionOrderWithPnL) => {
        const upnl = record.unrealized_pnl_usdt ?? record.unrealized_pnl;
        return (
          <Space direction="vertical" size={0} style={{ textAlign: "right" }}>
            <OrderPnlDisplay
              nativeValue={record.unrealized_pnl_native}
              usdtValue={upnl}
              asset={record.pnl_asset ?? pnlAsset}
              coinMargined={isCoinMargined && !isSpot}
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
    });
  }

  cols.push({
    title: "已实现盈亏",
    dataIndex: "realized_pnl",
    align: "right",
    width: 140,
    sorter: numericSorter("realized_pnl"),
    sortOrder: sortOrderFor("realized_pnl"),
    render: (_: number, record: PositionOrderWithPnL) => (
      <OrderPnlDisplay
        nativeValue={record.realized_pnl_native}
        usdtValue={record.realized_pnl_usdt ?? record.realized_pnl}
        asset={record.pnl_asset ?? pnlAsset}
        coinMargined={isCoinMargined && !isSpot}
      />
    ),
  });

  if (!isHistory && !isSpot) {
    cols.push(
      {
        title: "杠杆",
        dataIndex: "leverage",
        align: "right",
        width: 80,
        render: (v: number) => <span className="posi-numeric">{v}x</span>,
      },
      {
        title: "保证金",
        dataIndex: "margin",
        align: "right",
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
        align: "right",
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
        align: "right",
        width: 120,
        render: (v: number | null) => (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {v !== null ? fmtPrice(v) : "—"}
          </Text>
        ),
      }
    );
  }

  cols.push({
    title: "创建时间",
    dataIndex: "created_at",
    align: "right",
    width: 100,
    sorter: numericSorter("created_at"),
    sortOrder: sortOrderFor("created_at"),
    render: (v: string) => (
      <RelativeTime value={v} style={{ fontSize: 12 }} />
    ),
  });

  if (isHistory) {
    cols.push({
      title: isSpot ? "卖出时间" : "平仓时间",
      dataIndex: "updated_at",
      align: "right",
      width: 100,
      sorter: numericSorter("updated_at"),
      sortOrder: sortOrderFor("updated_at"),
      render: (v: string) => (
        <RelativeTime value={v} style={{ fontSize: 12 }} />
      ),
    });
  }

  cols.push({
    title: "操作",
    key: "actions",
    width: isHistory ? 80 : 120,
    fixed: "right",
    render: (_: unknown, record: PositionOrderWithPnL) => (
      <Space size="small">
        {!isHistory && (
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(record)}
          >
            编辑
          </Button>
        )}
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => onDelete(record.id, isHistory)}
        >
          删除
        </Button>
      </Space>
    ),
  });

  return cols;
}

interface OrderSectionProps {
  variant: OrderSectionVariant;
  title: string;
  hideHeader?: boolean;
  orders: PositionOrderWithPnL[];
  sort: OrderSortState;
  onSortChange: (sort: OrderSortState) => void;
  isLoading: boolean;
  isMobile: boolean;
  isSpot: boolean;
  isCoinMargined: boolean;
  pnlAsset: string | null;
  onEdit: (order: PositionOrderWithPnL) => void;
  onDelete: (orderId: number, isHistory: boolean) => void;
  emptyText: string;
  mobileSortOptions: readonly { label: string; value: string }[];
}

function OrderSection({
  variant,
  title,
  hideHeader = false,
  orders,
  sort,
  onSortChange,
  isLoading,
  isMobile,
  isSpot,
  isCoinMargined,
  pnlAsset,
  onEdit,
  onDelete,
  emptyText,
  mobileSortOptions,
}: OrderSectionProps) {
  const isHistory = variant === "history";
  const sortedOrders = useMemo(
    () => sortOrders(orders, sort),
    [orders, sort]
  );

  const columns = useMemo(
    () =>
      buildColumns({
        variant,
        isSpot,
        isCoinMargined,
        pnlAsset,
        sort,
        onEdit,
        onDelete,
      }),
    [variant, isSpot, isCoinMargined, pnlAsset, sort, onEdit, onDelete]
  );

  const handleTableChange: TableProps<PositionOrderWithPnL>["onChange"] = (
    _pagination,
    _filters,
    sorter
  ) => {
    const single = Array.isArray(sorter) ? sorter[0] : sorter;
    if (!single?.field || !single.order) {
      onSortChange(
        variant === "history" ? HISTORY_DEFAULT_SORT : ACTIVE_DEFAULT_SORT
      );
      return;
    }
    onSortChange(
      sortFromAnt(single.field as OrderSortField, single.order)
    );
  };

  const renderMobileOrderCard = (order: PositionOrderWithPnL) => (
    <Card
      key={order.id}
      size="small"
      style={{ marginBottom: 0 }}
      styles={{ body: { padding: 12 } }}
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
              {isSpot ? "买入数量" : "开仓数量"}
            </Text>
            <div>
              <span className="posi-numeric">{fmtQty(order.open_qty)}</span>
            </div>
          </Col>
          {!isHistory && (
            <Col span={12}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                剩余数量
              </Text>
              <div>
                <span className="posi-numeric">
                  {fmtQty(order.remaining_qty)}
                </span>
              </div>
            </Col>
          )}
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isSpot ? "买入价" : "开仓价"}
            </Text>
            <div>
              <span className="posi-numeric">{fmtPrice(order.entry_price)}</span>
            </div>
          </Col>
          <Col span={12}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isHistory
                ? isSpot
                  ? "卖出价"
                  : "平仓价"
                : order.status === "partial"
                  ? "平仓 / 当前"
                  : "当前价"}
            </Text>
            <div>
              {isHistory
                ? renderHistoryPriceCell(order)
                : renderActivePriceCell(order)}
            </div>
          </Col>
          {!isHistory && (
            <Col span={24}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                未实现盈亏
              </Text>
              <div>
                <OrderPnlDisplay
                  nativeValue={order.unrealized_pnl_native}
                  usdtValue={
                    order.unrealized_pnl_usdt ?? order.unrealized_pnl
                  }
                  asset={order.pnl_asset ?? pnlAsset}
                  coinMargined={isCoinMargined && !isSpot}
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
          )}
          <Col span={24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              已实现盈亏
            </Text>
            <div>
              <OrderPnlDisplay
                nativeValue={order.realized_pnl_native}
                usdtValue={order.realized_pnl_usdt ?? order.realized_pnl}
                asset={order.pnl_asset ?? pnlAsset}
                coinMargined={isCoinMargined && !isSpot}
              />
            </div>
          </Col>
          {!isHistory && !isSpot && (
            <>
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
                    coinMargined={isCoinMargined && !isSpot}
                  />
                </div>
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  MMR
                </Text>
                <div>
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    {order.mmr !== null
                      ? `${(order.mmr * 100).toFixed(2)}%`
                      : "—"}
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
            </>
          )}
          <Col span={isHistory ? 12 : 24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              创建
            </Text>
            <div>
              <RelativeTime value={order.created_at} style={{ fontSize: 12 }} />
            </div>
          </Col>
          {isHistory && (
            <Col span={12}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {isSpot ? "卖出" : "平仓"}
              </Text>
              <div>
                <RelativeTime value={order.updated_at} style={{ fontSize: 12 }} />
              </div>
            </Col>
          )}
        </Row>

        <Space
          size="small"
          style={{ width: "100%", justifyContent: "flex-end" }}
        >
          {!isHistory && (
            <Button
              type="default"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEdit(order)}
            >
              编辑
            </Button>
          )}
          <Button
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => onDelete(order.id, isHistory)}
          >
            删除
          </Button>
        </Space>
      </Space>
    </Card>
  );

  return (
    <div style={{ marginBottom: hideHeader ? 0 : 16 }}>
      {!hideHeader && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 8,
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <Space size={8}>
            <Text strong style={{ fontSize: 13 }}>
              {title}
            </Text>
            <Badge
              count={orders.length}
              showZero
              color={isHistory ? "default" : "green"}
              style={{ backgroundColor: isHistory ? "#d9d9d9" : undefined }}
            />
          </Space>
          {isMobile && orders.length > 0 && (
            <Select
              size="small"
              style={{ minWidth: 140 }}
              value={mobileSortValue(sort)}
              options={[...mobileSortOptions]}
              onChange={(value) => onSortChange(parseMobileSortValue(value))}
            />
          )}
        </div>
      )}
      {hideHeader && isMobile && orders.length > 0 && (
        <div style={{ marginBottom: 8, display: "flex", justifyContent: "flex-end" }}>
          <Select
            size="small"
            style={{ minWidth: 140 }}
            value={mobileSortValue(sort)}
            options={[...mobileSortOptions]}
            onChange={(value) => onSortChange(parseMobileSortValue(value))}
          />
        </div>
      )}

      {isMobile ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {isLoading ? (
            <Text type="secondary">加载中…</Text>
          ) : sortedOrders.length === 0 ? (
            <Text type="secondary">{emptyText}</Text>
          ) : (
            sortedOrders.map(renderMobileOrderCard)
          )}
        </div>
      ) : (
        <Table
          rowKey="id"
          columns={columns}
          dataSource={sortedOrders}
          loading={isLoading}
          pagination={false}
          size="small"
          scroll={{ x: isHistory ? 1100 : 1520 }}
          locale={{ emptyText }}
          onChange={handleTableChange}
          showSorterTooltip={false}
        />
      )}
    </div>
  );
}

export function PositionOrdersTable({
  positionId,
  isCoinMargined = false,
  pnlAsset = null,
  isSpot = false,
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
  const [activeSort, setActiveSort] = useState<OrderSortState>(
    ACTIVE_DEFAULT_SORT
  );
  const [historySort, setHistorySort] = useState<OrderSortState>(
    HISTORY_DEFAULT_SORT
  );
  const [historyExpanded, setHistoryExpanded] = useState<string[]>([]);

  const { active, history } = useMemo(
    () => partitionOrders(orders ?? []),
    [orders]
  );

  useEffect(() => {
    if (active.length === 0 && history.length > 0) {
      setHistoryExpanded(["history"]);
    } else if (active.length > 0) {
      setHistoryExpanded([]);
    }
  }, [active.length, history.length]);

  const defaultClosePrice = orders?.[0]?.mark_price;
  const hasOpenQty = active.length > 0;

  const handleDelete = (orderId: number, isHistory: boolean) => {
    confirm({
      title: "确认删除",
      icon: <ExclamationCircleOutlined />,
      content: isHistory
        ? "确定要删除这条历史订单吗？此操作不可撤销。"
        : "确定要删除这个订单吗？此操作不可撤销。",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        try {
          await deleteMutation.mutateAsync(orderId);
          message.success("订单已删除");
        } catch {
          message.error("删除失败");
        }
      },
    });
  };

  if (error) {
    return (
      <div style={{ padding: 16, color: "#ff4d4f" }}>
        加载订单失败: {error.message}
      </div>
    );
  }

  const historyTitle = isSpot ? "已卖出批次" : "历史订单";
  const activeTitle = "持仓中";
  const isEmpty = !isLoading && active.length === 0 && history.length === 0;

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
        <Text strong>{isSpot ? "买入批次" : "订单明细"}</Text>
        <Space size="small" wrap>
          <Button
            size="small"
            icon={<ScissorOutlined />}
            onClick={() => setIsCloseModalOpen(true)}
            disabled={!hasOpenQty}
          >
            {isSpot ? "FIFO 卖出" : "FIFO 平仓"}
          </Button>
          <Button
            size="small"
            icon={<SwapOutlined />}
            onClick={() => setIsSpecifiedCloseModalOpen(true)}
            disabled={!hasOpenQty}
          >
            {isSpot ? "指定卖出" : "指定配对"}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            {isSpot ? "添加批次" : "添加订单"}
          </Button>
        </Space>
      </div>

      {isEmpty ? (
        <Text type="secondary">暂无订单数据</Text>
      ) : (
        <>
          <OrderSection
            variant="active"
            title={activeTitle}
            orders={active}
            sort={activeSort}
            onSortChange={setActiveSort}
            isLoading={isLoading}
            isMobile={isMobile}
            isSpot={isSpot}
            isCoinMargined={isCoinMargined}
            pnlAsset={pnlAsset}
            onEdit={setEditingOrder}
            onDelete={handleDelete}
            emptyText="暂无持仓中订单"
            mobileSortOptions={ACTIVE_MOBILE_SORT_OPTIONS}
          />

          {(history.length > 0 || isLoading) && (
            <Collapse
              activeKey={historyExpanded}
              onChange={(keys) =>
                setHistoryExpanded(Array.isArray(keys) ? keys : [keys])
              }
              items={[
                {
                  key: "history",
                  label: (
                    <Space size={8}>
                      <Text strong style={{ fontSize: 13 }}>
                        {historyTitle}
                      </Text>
                      <Badge
                        count={history.length}
                        showZero
                        style={{ backgroundColor: "#d9d9d9" }}
                      />
                    </Space>
                  ),
                  children: (
                    <OrderSection
                      variant="history"
                      title={historyTitle}
                      hideHeader
                      orders={history}
                      sort={historySort}
                      onSortChange={setHistorySort}
                      isLoading={isLoading}
                      isMobile={isMobile}
                      isSpot={isSpot}
                      isCoinMargined={isCoinMargined}
                      pnlAsset={pnlAsset}
                      onEdit={setEditingOrder}
                      onDelete={handleDelete}
                      emptyText="暂无历史订单"
                      mobileSortOptions={HISTORY_MOBILE_SORT_OPTIONS}
                    />
                  ),
                },
              ]}
              ghost
              style={{ background: "transparent" }}
            />
          )}
        </>
      )}

      <PositionOrderModal
        open={isCreateModalOpen}
        positionId={positionId}
        marginAsset={isCoinMargined ? pnlAsset : null}
        isSpot={isSpot}
        onCancel={() => setIsCreateModalOpen(false)}
        onSuccess={() => setIsCreateModalOpen(false)}
      />

      <PositionOrderModal
        open={!!editingOrder}
        positionId={positionId}
        order={editingOrder || undefined}
        marginAsset={isCoinMargined ? pnlAsset : null}
        isSpot={isSpot}
        onCancel={() => setEditingOrder(null)}
        onSuccess={() => setEditingOrder(null)}
      />

      <PositionCloseFifoModal
        open={isCloseModalOpen}
        positionId={positionId}
        defaultClosePrice={defaultClosePrice}
        isSpot={isSpot}
        onCancel={() => setIsCloseModalOpen(false)}
        onSuccess={() => setIsCloseModalOpen(false)}
      />

      <PositionCloseSpecifiedModal
        open={isSpecifiedCloseModalOpen}
        positionId={positionId}
        defaultClosePrice={defaultClosePrice}
        isSpot={isSpot}
        onCancel={() => setIsSpecifiedCloseModalOpen(false)}
        onSuccess={() => setIsSpecifiedCloseModalOpen(false)}
      />
    </div>
  );
}
