import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Form,
  InputNumber,
  Modal,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { usePositionOrders, useSpecifiedClosePosition } from "@/api/hooks";
import type { PositionOrderWithPnL } from "@/api/types";
import { fmtPrice, fmtQty } from "@/utils/format";

const { Text } = Typography;

const QTY_EPS = 1e-9;

interface PositionCloseSpecifiedModalProps {
  open: boolean;
  positionId: number;
  defaultClosePrice?: number;
  onCancel: () => void;
  onSuccess: () => void;
}

export function PositionCloseSpecifiedModal({
  open,
  positionId,
  defaultClosePrice,
  onCancel,
  onSuccess,
}: PositionCloseSpecifiedModalProps) {
  const [form] = Form.useForm();
  const closeMutation = useSpecifiedClosePosition();
  const { data: orders } = usePositionOrders(positionId);
  const [qtyByOrderId, setQtyByOrderId] = useState<Record<number, number>>({});

  const openOrders = useMemo(() => {
    const rows = (orders ?? []).filter((o) => o.remaining_qty > QTY_EPS);
    return [...rows].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime() ||
        a.id - b.id
    );
  }, [orders]);

  const allocatedTotal = useMemo(
    () =>
      openOrders.reduce(
        (sum, o) => sum + (qtyByOrderId[o.id] ?? 0),
        0
      ),
    [openOrders, qtyByOrderId]
  );

  useEffect(() => {
    if (open) {
      setQtyByOrderId({});
      form.resetFields();
      form.setFieldsValue({
        close_price: defaultClosePrice ?? undefined,
      });
    }
  }, [open, defaultClosePrice, form]);

  const columns: ColumnsType<PositionOrderWithPnL> = [
    {
      title: "订单 ID",
      dataIndex: "id",
      width: 88,
      render: (id: number) => <Text code>{id}</Text>,
    },
    {
      title: "剩余",
      dataIndex: "remaining_qty",
      width: 120,
      render: (q: number) => (
        <span className="posi-numeric">{fmtQty(q)}</span>
      ),
    },
    {
      title: "开仓价",
      dataIndex: "entry_price",
      width: 120,
      render: (p: number) => (
        <span className="posi-numeric">{fmtPrice(p)}</span>
      ),
    },
    {
      title: "本次平仓",
      key: "allocate",
      width: 160,
      render: (_, record) => (
        <InputNumber
          size="small"
          min={0}
          max={record.remaining_qty}
          step={0.001}
          precision={8}
          style={{ width: "100%" }}
          placeholder="0"
          value={
            qtyByOrderId[record.id] !== undefined
              ? qtyByOrderId[record.id]
              : undefined
          }
          onChange={(v) => {
            setQtyByOrderId((prev) => {
              const next = { ...prev };
              if (v === null || v === undefined) {
                delete next[record.id];
              } else {
                next[record.id] = v;
              }
              return next;
            });
          }}
        />
      ),
    },
  ];

  const handleSubmit = async () => {
    try {
      const { close_price } = await form.validateFields();
      const legs = openOrders
        .map((o) => {
          const q = qtyByOrderId[o.id] ?? 0;
          if (q > QTY_EPS) {
            if (q - o.remaining_qty > QTY_EPS) {
              throw new Error(
                `订单 ${o.id}：分配数量不能超过剩余 ${fmtQty(o.remaining_qty)}`
              );
            }
            return { open_order_id: o.id, qty: q };
          }
          return null;
        })
        .filter(
          (x): x is { open_order_id: number; qty: number } => x !== null
        );

      if (legs.length === 0) {
        message.warning("请至少在一个订单上填写大于 0 的平仓数量");
        return;
      }

      if (allocatedTotal <= QTY_EPS) {
        message.warning("平仓数量总和必须大于 0");
        return;
      }

      const result = await closeMutation.mutateAsync({
        positionId,
        payload: {
          close_qty: allocatedTotal,
          close_price,
          legs,
          source: "manual",
        },
      });
      message.success(
        `平仓成功，已实现盈亏 ${result.realized_pnl.toFixed(2)}`
      );
      onSuccess();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) {
        return;
      }
      if (err instanceof Error && !("response" in err)) {
        message.error(err.message);
        return;
      }
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "平仓失败";
      message.error(detail);
    }
  };

  return (
    <Modal
      title="指定配对平仓"
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={closeMutation.isPending}
      okText="确认平仓"
      cancelText="取消"
      width={720}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="自行选择在各开仓订单上分配的数量；匹配顺序与表格行顺序一致。"
        description={
          <span>
            当前分配合计：
            <span className="posi-numeric">{fmtQty(allocatedTotal)}</span>
            （将作为本次平仓总量提交）
          </span>
        }
      />

      <Form form={form} layout="vertical">
        <Form.Item
          name="close_price"
          label="平仓价"
          rules={[
            { required: true, message: "请输入平仓价" },
            { type: "number", min: 0.00000001, message: "价格必须大于 0" },
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder={
              defaultClosePrice ? fmtPrice(defaultClosePrice) : "50000.00"
            }
            step={0.01}
            precision={8}
            min={0}
          />
        </Form.Item>
      </Form>

      <Table<PositionOrderWithPnL>
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={openOrders}
        pagination={false}
        locale={{ emptyText: "没有可分配的剩余持仓订单" }}
        scroll={{ x: 520 }}
      />

      <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 12 }}>
        与 FIFO 相同，每条消耗会写入 position_order_matches 供已实现盈亏与审计使用。
      </Text>
    </Modal>
  );
}
