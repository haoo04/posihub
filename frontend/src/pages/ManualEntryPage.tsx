import { useMemo } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, PlusOutlined, SaveOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { PageHeader } from "@/components/PageHeader";
import { useAccounts, useCreateManualSnapshot } from "@/api/hooks";
import type { ManualSnapshotCreate, PositionSide } from "@/api/types";

const { Text } = Typography;

const SIDE_OPTIONS: { value: PositionSide; label: string }[] = [
  { value: "long", label: "LONG" },
  { value: "short", label: "SHORT" },
  { value: "net", label: "NET" },
];

interface FormValues {
  account_id: number;
  snapshot_date: dayjs.Dayjs;
  asset: string;
  total_equity?: number | null;
  total_unrealized_pnl?: number;
  total_available?: number;
  balances: { asset: string; equity: number; available?: number; frozen?: number }[];
  positions: {
    canonical_symbol: string;
    side: PositionSide;
    qty: number;
    entry_price: number;
    mark_price: number;
    unrealized_pnl?: number;
  }[];
  operator?: string;
}

export function ManualEntryPage() {
  const accounts = useAccounts();
  const create = useCreateManualSnapshot();
  const [form] = Form.useForm<FormValues>();

  const accountOptions = useMemo(
    () =>
      (accounts.data ?? []).map((a) => ({
        value: a.id,
        label: `${a.account_name}${a.is_simulated ? "（模拟）" : ""}`,
      })),
    [accounts.data]
  );

  const onSubmit = async () => {
    const values = await form.validateFields();
    const payload: ManualSnapshotCreate = {
      account_id: values.account_id,
      snapshot_date: values.snapshot_date.format("YYYY-MM-DD"),
      asset: (values.asset || "USDT").toUpperCase(),
      total_equity: values.total_equity ?? null,
      total_unrealized_pnl: values.total_unrealized_pnl ?? 0,
      total_available: values.total_available ?? 0,
      balances: (values.balances ?? []).map((b) => ({
        asset: b.asset.toUpperCase(),
        equity: b.equity,
        available: b.available ?? 0,
        frozen: b.frozen ?? 0,
      })),
      positions: (values.positions ?? []).map((p) => ({
        canonical_symbol: p.canonical_symbol.toUpperCase(),
        side: p.side,
        qty: p.qty,
        entry_price: p.entry_price,
        mark_price: p.mark_price,
        unrealized_pnl: p.unrealized_pnl ?? 0,
      })),
      operator: values.operator || "local",
    };

    try {
      const res = await create.mutateAsync(payload);
      message.success(
        `已写入：账户快照 ${res.accounts_written}，仓位 ${res.positions_written}，余额 ${res.balances_written}`
      );
      form.resetFields([
        "balances",
        "positions",
        "total_equity",
        "total_unrealized_pnl",
        "total_available",
      ]);
    } catch (e) {
      message.error((e as Error).message ?? "保存失败");
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="手动录入"
        description="补录某日账户/仓位快照；模拟账户可在此直接调整余额与持仓"
        extra={
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={create.isPending}
            onClick={onSubmit}
          >
            保存快照
          </Button>
        }
      />

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          snapshot_date: dayjs(),
          asset: "USDT",
          balances: [],
          positions: [],
          operator: "local",
        }}
      >
        <Card
          title="基础信息"
          bodyStyle={{ padding: 20 }}
          style={{ borderRadius: 12 }}
        >
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item
                label="账户"
                name="account_id"
                rules={[{ required: true, message: "请选择账户" }]}
              >
                <Select
                  showSearch
                  placeholder="选择目标账户"
                  options={accountOptions}
                  optionFilterProp="label"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item
                label="快照日期"
                name="snapshot_date"
                rules={[{ required: true }]}
              >
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={4}>
              <Form.Item label="结算资产" name="asset">
                <Input placeholder="USDT" />
              </Form.Item>
            </Col>
            <Col xs={24} md={4}>
              <Form.Item label="操作人" name="operator">
                <Input placeholder="local" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item
                label="总权益（可选，留空则按余额求和）"
                name="total_equity"
              >
                <InputNumber
                  style={{ width: "100%" }}
                  min={0}
                  placeholder="如 12345.67"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item label="未实现盈亏" name="total_unrealized_pnl">
                <InputNumber style={{ width: "100%" }} placeholder="0" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item label="可用余额" name="total_available">
                <InputNumber
                  style={{ width: "100%" }}
                  min={0}
                  placeholder="0"
                />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card
          title={
            <Space size={8} align="center">
              <span>余额明细</span>
              <Text type="secondary" style={{ fontSize: 12 }}>
                模拟账户写入后会立即生效
              </Text>
            </Space>
          }
          bodyStyle={{ padding: 20 }}
          style={{ borderRadius: 12, marginTop: 16 }}
        >
          <Form.List name="balances">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Row
                    key={field.key}
                    gutter={12}
                    align="middle"
                    style={{ marginBottom: 8 }}
                  >
                    <Col span={5}>
                      <Form.Item
                        name={[field.name, "asset"]}
                        label="资产"
                        rules={[{ required: true, message: "请输入资产" }]}
                        style={{ marginBottom: 0 }}
                      >
                        <Input placeholder="USDT" />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item
                        name={[field.name, "equity"]}
                        label="权益"
                        rules={[{ required: true, message: "请输入权益" }]}
                        style={{ marginBottom: 0 }}
                      >
                        <InputNumber
                          style={{ width: "100%" }}
                          placeholder="0"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item
                        name={[field.name, "available"]}
                        label="可用"
                        style={{ marginBottom: 0 }}
                      >
                        <InputNumber
                          style={{ width: "100%" }}
                          placeholder="0"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item
                        name={[field.name, "frozen"]}
                        label="冻结"
                        style={{ marginBottom: 0 }}
                      >
                        <InputNumber
                          style={{ width: "100%" }}
                          placeholder="0"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={2}>
                      <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => remove(field.name)}
                      />
                    </Col>
                  </Row>
                ))}
                <Button
                  block
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({ asset: "USDT", equity: 0, available: 0, frozen: 0 })
                  }
                >
                  添加余额
                </Button>
              </>
            )}
          </Form.List>
        </Card>

        <Card
          title="仓位明细"
          bodyStyle={{ padding: 20 }}
          style={{ borderRadius: 12, marginTop: 16 }}
        >
          <Form.List name="positions">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <div key={field.key} style={{ marginBottom: 12 }}>
                    <Row gutter={12} align="middle">
                      <Col span={6}>
                        <Form.Item
                          name={[field.name, "canonical_symbol"]}
                          label="交易对"
                          rules={[{ required: true, message: "请输入交易对" }]}
                          style={{ marginBottom: 0 }}
                        >
                          <Input placeholder="BTC-USDT-PERP" />
                        </Form.Item>
                      </Col>
                      <Col span={3}>
                        <Form.Item
                          name={[field.name, "side"]}
                          label="方向"
                          rules={[{ required: true, message: "请选择方向" }]}
                          style={{ marginBottom: 0 }}
                        >
                          <Select options={SIDE_OPTIONS} />
                        </Form.Item>
                      </Col>
                      <Col span={3}>
                        <Form.Item
                          name={[field.name, "qty"]}
                          label="数量"
                          rules={[{ required: true, message: "请输入数量" }]}
                          style={{ marginBottom: 0 }}
                        >
                          <InputNumber
                            style={{ width: "100%" }}
                            placeholder="0"
                          />
                        </Form.Item>
                      </Col>
                      <Col span={4}>
                        <Form.Item
                          name={[field.name, "entry_price"]}
                          label="开仓价"
                          rules={[{ required: true, message: "请输入开仓价" }]}
                          style={{ marginBottom: 0 }}
                        >
                          <InputNumber
                            style={{ width: "100%" }}
                            placeholder="0"
                          />
                        </Form.Item>
                      </Col>
                      <Col span={3}>
                        <Form.Item
                          name={[field.name, "mark_price"]}
                          label="标记价"
                          rules={[{ required: true, message: "请输入标记价" }]}
                          style={{ marginBottom: 0 }}
                        >
                          <InputNumber
                            style={{ width: "100%" }}
                            placeholder="0"
                          />
                        </Form.Item>
                      </Col>
                      <Col span={3}>
                        <Form.Item
                          name={[field.name, "unrealized_pnl"]}
                          label="未实现盈亏"
                          style={{ marginBottom: 0 }}
                        >
                          <InputNumber
                            style={{ width: "100%" }}
                            placeholder="0"
                          />
                        </Form.Item>
                      </Col>
                      <Col span={2}>
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => remove(field.name)}
                        />
                      </Col>
                    </Row>
                  </div>
                ))}
                <Divider style={{ margin: "12px 0" }} />
                <Button
                  block
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      canonical_symbol: "",
                      side: "long",
                      qty: 0,
                      entry_price: 0,
                      mark_price: 0,
                      unrealized_pnl: 0,
                    })
                  }
                >
                  添加仓位
                </Button>
              </>
            )}
          </Form.List>
        </Card>
      </Form>
    </Space>
  );
}
