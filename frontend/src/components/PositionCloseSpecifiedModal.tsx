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
import type { PositionOrderWithPnL, QuantityMode } from "@/api/types";
import { fmtContractValue, fmtPrice, fmtQuantity } from "@/utils/format";
import { quantityTolerance } from "@/utils/positionOrders";

const { Text } = Typography;

const QTY_EPS = 1e-9;

interface PositionCloseSpecifiedModalProps {
  open: boolean;
  positionId: number;
  defaultClosePrice?: number;
  isSpot?: boolean;
  quantityMode?: QuantityMode;
  quantityUnit?: string;
  baseAsset?: string;
  onCancel: () => void;
  onSuccess: () => void;
}

export function PositionCloseSpecifiedModal({
  open,
  positionId,
  defaultClosePrice,
  isSpot = false,
  quantityMode = "base",
  quantityUnit = "",
  baseAsset = "",
  onCancel,
  onSuccess,
}: PositionCloseSpecifiedModalProps) {
  const [form] = Form.useForm();
  const closeMutation = useSpecifiedClosePosition();
  const { data: orders } = usePositionOrders(positionId);
  const [qtyByOrderId, setQtyByOrderId] = useState<Record<number, number>>({});
  const inverse = quantityMode === "quote_contract";
  const closePrice = Form.useWatch("close_price", form);

  const openOrders = useMemo(() => {
    const rows = (orders ?? []).filter((o) => o.remaining_qty > (inverse ? 0 : QTY_EPS));
    return [...rows].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime() ||
        a.id - b.id
    );
  }, [orders, inverse]);

  const allocatedTotal = useMemo(
    () =>
      openOrders.reduce(
        (sum, o) => sum + (qtyByOrderId[o.id] ?? 0),
        0
      ),
    [openOrders, qtyByOrderId]
  );

  const preview = inverse ? fmtContractValue(allocatedTotal, closePrice, baseAsset) : null;

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
      title: `剩余${quantityUnit ? ` (${quantityUnit})` : ""}`,
      dataIndex: "remaining_qty",
      width: 120,
      render: (q: number) => (
        <span className="posi-numeric">{fmtQuantity(q, quantityUnit)}</span>
      ),
    },
    {
      title: isSpot ? "买入价" : "开仓价",
      dataIndex: "entry_price",
      width: 120,
      render: (p: number) => (
        <span className="posi-numeric">{fmtPrice(p)}</span>
      ),
    },
    {
      title: inverse ? "本次平仓 (USD)" : isSpot ? "本次卖出" : "本次平仓",
      key: "allocate",
      width: 160,
      render: (_, record) => (
        <InputNumber
          size="small"
          min={0}
          max={record.remaining_qty + (inverse ? quantityTolerance(record) : 0)}
          step={inverse ? 1 : 0.001}
          precision={inverse ? undefined : 8}
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
          if (q > (inverse ? 0 : QTY_EPS)) {
            if (q - o.remaining_qty > quantityTolerance(o)) {
              throw new Error(
                `订单 ${o.id}：分配数量不能超过剩余 ${fmtQuantity(o.remaining_qty, quantityUnit)}`
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
        message.warning(
          isSpot
            ? "请至少在一个批次上填写大于 0 的卖出数量"
            : "请至少在一个订单上填写大于 0 的平仓数量"
        );
        return;
      }

      if (allocatedTotal <= (inverse ? 0 : QTY_EPS)) {
        message.warning(isSpot ? "卖出数量总和必须大于 0" : "平仓数量总和必须大于 0");
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
        `${isSpot ? "卖出" : "平仓"}成功，已实现盈亏 ${result.realized_pnl.toFixed(2)}`
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
          ?.detail ?? (isSpot ? "卖出失败" : "平仓失败");
      message.error(detail);
    }
  };

  return (
    <Modal
      title={isSpot ? "指定批次卖出" : "指定配对平仓"}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={closeMutation.isPending}
      okText={isSpot ? "确认卖出" : "确认平仓"}
      cancelText="取消"
      width={720}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          isSpot
            ? "自行选择在各买入批次上分配的数量；匹配顺序与表格行顺序一致。"
            : "自行选择在各开仓订单上分配的数量；匹配顺序与表格行顺序一致。"
        }
        description={
          <span>
            当前分配合计：
            <span className="posi-numeric">{fmtQuantity(allocatedTotal, quantityUnit)}</span>
            （将作为本次{isSpot ? "卖出" : "平仓"}总量提交）
          </span>
        }
      />

      <Form form={form} layout="vertical">
        <Form.Item
          name="close_price"
          label={isSpot ? "卖出价" : "平仓价"}
          rules={[
            { required: true, message: isSpot ? "请输入卖出价" : "请输入平仓价" },
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
        locale={{ emptyText: isSpot ? "没有可分配的剩余买入批次" : "没有可分配的剩余持仓订单" }}
        scroll={{ x: 520 }}
      />

      <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 12 }}>
        {preview ? `平仓成交额约 ${preview}。` : ""}已实现盈亏按每条订单的开仓价计算。
      </Text>
    </Modal>
  );
}
