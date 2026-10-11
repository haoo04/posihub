import { useEffect, useMemo } from "react";
import { Alert, Form, InputNumber, Modal, Typography, message } from "antd";
import { useFifoClosePosition, usePositionOrders } from "@/api/hooks";
import { fmtContractValue, fmtPrice, fmtQuantity } from "@/utils/format";
import type { QuantityMode } from "@/api/types";
import { quantityTolerance } from "@/utils/positionOrders";

const { Text } = Typography;

interface PositionCloseFifoModalProps {
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

export function PositionCloseFifoModal({
  open,
  positionId,
  defaultClosePrice,
  isSpot = false,
  quantityMode = "base",
  quantityUnit = "",
  baseAsset = "",
  onCancel,
  onSuccess,
}: PositionCloseFifoModalProps) {
  const [form] = Form.useForm();
  const closeMutation = useFifoClosePosition();
  const { data: orders } = usePositionOrders(positionId);
  const inverse = quantityMode === "quote_contract";
  const closeQty = Form.useWatch("close_qty", form);
  const closePrice = Form.useWatch("close_price", form);
  const preview = inverse ? fmtContractValue(closeQty, closePrice, baseAsset) : null;

  const totalRemaining = useMemo(
    () => (orders ?? []).reduce((sum, o) => sum + o.remaining_qty, 0),
    [orders]
  );
  const tolerance = inverse
    ? (orders ?? []).reduce((sum, order) => sum + quantityTolerance(order), 0)
    : 1e-9;

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({
        close_qty: undefined,
        close_price: defaultClosePrice ?? undefined,
      });
    }
  }, [open, defaultClosePrice, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const result = await closeMutation.mutateAsync({
        positionId,
        payload: {
          close_qty: values.close_qty,
          close_price: values.close_price,
          source: "manual",
        },
      });
      message.success(
        `${isSpot ? "卖出" : "平仓"}成功，已实现盈亏 ${result.realized_pnl.toFixed(2)}`
      );
      onSuccess();
    } catch (err) {
      if (err instanceof Error && "errorFields" in err) {
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
      title={isSpot ? "FIFO 卖出" : "FIFO 平仓"}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={closeMutation.isPending}
      okText={isSpot ? "确认卖出" : "确认平仓"}
      cancelText="取消"
      width={520}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={isSpot ? "按买入时间升序消耗剩余数量。" : "按订单 created_at 升序消耗剩余数量。"}
        description={
          <span>
            {isSpot ? "可卖总量" : "可平总量"}：
            <span className="posi-numeric">{fmtQuantity(totalRemaining, quantityUnit)}</span>
          </span>
        }
      />

      <Form form={form} layout="vertical">
        <Form.Item
          name="close_qty"
          label={inverse ? "平仓成交数量 (USD)" : isSpot ? "卖出数量" : "平仓数量"}
          extra={inverse ? `请填写 Bybit 的 Filled Quantity，不要填写 ${baseAsset} 成交额` : undefined}
          rules={[
            { required: true, message: isSpot ? "请输入卖出数量" : "请输入平仓数量" },
            { type: "number", min: inverse ? Number.MIN_VALUE : 0.00000001, message: "数量必须大于 0" },
            {
              validator: (_, value) =>
                value > totalRemaining + Math.max(1e-9, tolerance)
                  ? Promise.reject(new Error("超过可平总量"))
                  : Promise.resolve(),
            },
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder={inverse ? "65" : "0.5"}
            step={inverse ? 1 : 0.001}
            precision={inverse ? undefined : 8}
            min={0}
          />
        </Form.Item>

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

        {preview && <Text type="secondary" style={{ display: "block" }}>平仓成交额约 {preview}</Text>}
        <Text type="secondary" style={{ fontSize: 12 }}>
          已实现盈亏按每条订单的开仓价计算，显示为 USDT 等值。
        </Text>
      </Form>
    </Modal>
  );
}
