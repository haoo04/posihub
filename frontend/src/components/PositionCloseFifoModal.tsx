import { useEffect, useMemo } from "react";
import { Alert, Form, InputNumber, Modal, Typography, message } from "antd";
import { useFifoClosePosition, usePositionOrders } from "@/api/hooks";
import { fmtPrice, fmtQty } from "@/utils/format";

const { Text } = Typography;

interface PositionCloseFifoModalProps {
  open: boolean;
  positionId: number;
  defaultClosePrice?: number;
  isSpot?: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

export function PositionCloseFifoModal({
  open,
  positionId,
  defaultClosePrice,
  isSpot = false,
  onCancel,
  onSuccess,
}: PositionCloseFifoModalProps) {
  const [form] = Form.useForm();
  const closeMutation = useFifoClosePosition();
  const { data: orders } = usePositionOrders(positionId);

  const totalRemaining = useMemo(
    () => (orders ?? []).reduce((sum, o) => sum + o.remaining_qty, 0),
    [orders]
  );

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
            <span className="posi-numeric">{fmtQty(totalRemaining)}</span>
          </span>
        }
      />

      <Form form={form} layout="vertical">
        <Form.Item
          name="close_qty"
          label={isSpot ? "卖出数量" : "平仓数量"}
          rules={[
            { required: true, message: isSpot ? "请输入卖出数量" : "请输入平仓数量" },
            { type: "number", min: 0.00000001, message: "数量必须大于 0" },
            {
              validator: (_, value) =>
                value > totalRemaining + 1e-9
                  ? Promise.reject(new Error("超过可平总量"))
                  : Promise.resolve(),
            },
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder="0.5"
            step={0.001}
            precision={8}
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

        <Text type="secondary" style={{ fontSize: 12 }}>
          已实现盈亏会按每个被消耗的订单分别记录到 position_order_matches。
        </Text>
      </Form>
    </Modal>
  );
}
