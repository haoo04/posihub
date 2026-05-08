import { useState } from "react";
import { Button, Modal, Space, Table, Tag, Typography, message } from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { PnlText } from "./PnlText";
import { useDeletePositionOrder, usePositionOrders } from "@/api/hooks";
import type { PositionOrderWithPnL } from "@/api/types";
import { fmtPrice, fmtQty, fmtRelative } from "@/utils/format";
import { PositionOrderModal } from "./PositionOrderModal";

const { Text } = Typography;
const { confirm } = Modal;

interface PositionOrdersTableProps {
  positionId: number;
}

export function PositionOrdersTable({ positionId }: PositionOrdersTableProps) {
  const { data: orders, isLoading, error } = usePositionOrders(positionId);
  const deleteMutation = useDeletePositionOrder();
  const [editingOrder, setEditingOrder] = useState<PositionOrderWithPnL | null>(
    null
  );
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

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
      render: (v: string) => {
        const colorMap: Record<string, string> = {
          api: "blue",
          manual: "orange",
          simulated: "purple",
        };
        return <Tag color={colorMap[v] || "default"}>{v.toUpperCase()}</Tag>;
      },
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (v: string) => {
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
        return <Tag color={colorMap[v]}>{textMap[v] || v}</Tag>;
      },
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
      title: "当前价",
      dataIndex: "mark_price",
      align: "right" as const,
      width: 120,
      render: (v: number) => (
        <span className="posi-numeric">{fmtPrice(v)}</span>
      ),
    },
    {
      title: "未实现盈亏",
      dataIndex: "unrealized_pnl",
      align: "right" as const,
      width: 140,
      render: (v: number, record: PositionOrderWithPnL) => (
        <Space direction="vertical" size={0} style={{ textAlign: "right" }}>
          <PnlText value={v} />
          <Text
            type="secondary"
            style={{ fontSize: 11 }}
            className={v >= 0 ? "posi-positive" : "posi-negative"}
          >
            {v >= 0 ? "+" : ""}
            {record.unrealized_pnl_pct.toFixed(2)}%
          </Text>
        </Space>
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
          {v !== null ? fmtPrice(v) : "—"}
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
        <Text type="secondary" style={{ fontSize: 12 }}>
          {fmtRelative(v)}
        </Text>
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

  return (
    <div style={{ padding: "0 16px 16px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <Text strong>订单明细</Text>
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => setIsCreateModalOpen(true)}
        >
          添加订单
        </Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={orders || []}
        loading={isLoading}
        pagination={false}
        size="small"
        scroll={{ x: 1520 }}
        locale={{ emptyText: "暂无订单数据" }}
      />

      <PositionOrderModal
        open={isCreateModalOpen}
        positionId={positionId}
        onCancel={() => setIsCreateModalOpen(false)}
        onSuccess={() => setIsCreateModalOpen(false)}
      />

      <PositionOrderModal
        open={!!editingOrder}
        positionId={positionId}
        order={editingOrder || undefined}
        onCancel={() => setEditingOrder(null)}
        onSuccess={() => setEditingOrder(null)}
      />
    </div>
  );
}
