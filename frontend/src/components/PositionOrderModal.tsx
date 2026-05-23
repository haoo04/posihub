import { useEffect } from "react";
import { Form, Input, InputNumber, Modal, Select, message } from "antd";
import {
  useCreatePositionOrder,
  useUpdatePositionOrder,
} from "@/api/hooks";
import type {
  DataSource,
  PositionOrderCreate,
  PositionOrderUpdate,
  PositionOrderWithPnL,
} from "@/api/types";

interface PositionOrderModalProps {
  open: boolean;
  positionId: number;
  order?: PositionOrderWithPnL;
  marginAsset?: string | null;
  onCancel: () => void;
  onSuccess: () => void;
}

export function PositionOrderModal({
  open,
  positionId,
  order,
  marginAsset = null,
  onCancel,
  onSuccess,
}: PositionOrderModalProps) {
  const [form] = Form.useForm();
  const createMutation = useCreatePositionOrder();
  const updateMutation = useUpdatePositionOrder();
  const isEdit = !!order;

  useEffect(() => {
    if (open && order) {
      form.setFieldsValue({
        source: order.source,
        source_order_id: order.source_order_id || "",
        open_qty: order.open_qty,
        remaining_qty: order.remaining_qty,
        entry_price: order.entry_price,
        leverage: order.leverage,
        margin: order.margin,
        mmr: order.mmr ? order.mmr * 100 : null,
        liquidation_price: order.liquidation_price,
      });
    } else if (open) {
      form.resetFields();
      form.setFieldsValue({
        source: "manual",
        leverage: 1,
      });
    }
  }, [open, order, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      if (isEdit && order) {
        const update: PositionOrderUpdate = {
          open_qty: values.open_qty,
          remaining_qty: values.remaining_qty,
          entry_price: values.entry_price,
          leverage: values.leverage,
          margin: values.margin || null,
          mmr: values.mmr ? values.mmr / 100 : null,
          liquidation_price: values.liquidation_price || null,
        };

        await updateMutation.mutateAsync({ id: order.id, update });
        message.success("订单已更新");
      } else {
        const payload: PositionOrderCreate = {
          position_id: positionId,
          source: values.source as DataSource,
          source_order_id: values.source_order_id || null,
          open_qty: values.open_qty,
          entry_price: values.entry_price,
          leverage: values.leverage,
          margin: values.margin || null,
          mmr: values.mmr ? values.mmr / 100 : null,
          liquidation_price: values.liquidation_price || null,
        };

        await createMutation.mutateAsync(payload);
        message.success("订单已创建");
      }

      form.resetFields();
      onSuccess();
    } catch (err) {
      if (err instanceof Error && "errorFields" in err) {
        // Form validation error, do nothing
        return;
      }
      message.error(isEdit ? "更新订单失败" : "创建订单失败");
    }
  };

  return (
    <Modal
      title={isEdit ? "编辑订单" : "添加订单"}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={createMutation.isPending || updateMutation.isPending}
      okText={isEdit ? "更新" : "创建"}
      cancelText="取消"
      width={600}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          name="source"
          label="来源"
          rules={[{ required: true, message: "请选择来源" }]}
        >
          <Select disabled={isEdit}>
            <Select.Option value="manual">手动录入</Select.Option>
            <Select.Option value="api">API 自动获取</Select.Option>
            <Select.Option value="simulated">模拟</Select.Option>
          </Select>
        </Form.Item>

        <Form.Item name="source_order_id" label="交易所订单ID">
          <Input placeholder="可选，交易所的原始订单ID" />
        </Form.Item>

        <Form.Item
          name="open_qty"
          label="开仓数量"
          rules={[
            { required: true, message: "请输入开仓数量" },
            { type: "number", min: 0.00001, message: "数量必须大于0" },
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder="0.001"
            step={0.001}
            precision={8}
          />
        </Form.Item>

        {isEdit && (
          <Form.Item
            name="remaining_qty"
            label="剩余数量"
            rules={[
              { required: true, message: "请输入剩余数量" },
              { type: "number", min: 0, message: "数量不能为负" },
            ]}
          >
            <InputNumber
              style={{ width: "100%" }}
              placeholder="0.001"
              step={0.001}
              precision={8}
            />
          </Form.Item>
        )}

        <Form.Item
          name="entry_price"
          label="开仓价"
          rules={[
            { required: true, message: "请输入开仓价" },
            { type: "number", min: 0.00001, message: "价格必须大于0" },
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder="50000.00"
            step={0.01}
            precision={8}
          />
        </Form.Item>

        <Form.Item
          name="leverage"
          label="杠杆"
          rules={[
            { required: true, message: "请输入杠杆" },
            { type: "number", min: 1, max: 125, message: "杠杆范围 1-125" },
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder="1"
            step={1}
            min={1}
            max={125}
          />
        </Form.Item>

        <Form.Item
          name="margin"
          label={
            marginAsset ? `保证金 (${marginAsset})` : "保证金 (USDT)"
          }
          tooltip={
            marginAsset
              ? `使用的保证金数量，以 ${marginAsset} 计`
              : "使用的保证金数量"
          }
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder="500.00"
            step={0.01}
            precision={8}
            min={0}
          />
        </Form.Item>

        <Form.Item
          name="mmr"
          label="维持保证金率 (%)"
          tooltip="Maintenance Margin Rate，如 0.5% 输入 0.5"
        >
          <InputNumber
            style={{ width: "100%" }}
            placeholder="0.5"
            step={0.1}
            precision={4}
            min={0}
            max={100}
          />
        </Form.Item>

        <Form.Item name="liquidation_price" label="强平价">
          <InputNumber
            style={{ width: "100%" }}
            placeholder="可选，强制平仓价格"
            step={0.01}
            precision={8}
            min={0}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
