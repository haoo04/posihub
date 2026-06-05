import { useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/StatusDot";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import RelativeTime from "@/components/RelativeTime";
import {
  useAccounts,
  useCreateAccount,
  useCreateExchange,
  useDeleteAccount,
  useExchanges,
  useSyncAccount,
} from "@/api/hooks";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import type { Account, AccountCreate, AccountType } from "@/api/types";

const { Text } = Typography;

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: "spot", label: "现货 Spot" },
  { value: "usdt_perp", label: "U 本位永续" },
  { value: "coin_perp", label: "币本位永续" },
  { value: "futures", label: "交割合约" },
  { value: "funding", label: "理财/资金" },
  { value: "simulated", label: "模拟账户" },
];

export function AccountsPage() {
  const { isMobile } = useBreakpoint();
  const accounts = useAccounts();
  const exchanges = useExchanges();
  const createAccount = useCreateAccount();
  const createExchange = useCreateExchange();
  const deleteAccount = useDeleteAccount();
  const syncAccount = useSyncAccount();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [exchangeModalOpen, setExchangeModalOpen] = useState(false);
  const [syncingAll, setSyncingAll] = useState(false);
  const [form] = Form.useForm<AccountCreate>();
  const [exchangeForm] = Form.useForm<{ name: string }>();

  const exchangeMap = new Map((exchanges.data ?? []).map((e) => [e.id, e.name]));

  const onSubmit = async () => {
    const values = await form.validateFields();
    try {
      await createAccount.mutateAsync({
        ...values,
        is_simulated: values.account_type === "simulated",
      });
      message.success("账户已创建");
      form.resetFields();
      setDrawerOpen(false);
    } catch (e) {
      message.error((e as Error).message ?? "创建失败");
    }
  };

  const onCreateExchange = async () => {
    const values = await exchangeForm.validateFields();
    try {
      await createExchange.mutateAsync({ name: values.name, enabled: true });
      message.success("交易所已新增");
      exchangeForm.resetFields();
      setExchangeModalOpen(false);
    } catch (e) {
      message.error((e as Error).message ?? "创建失败");
    }
  };

  const onSyncAll = async () => {
    const targets = (accounts.data ?? []).filter(
      (a) => a.enabled && !a.is_simulated
    );
    if (!targets.length) {
      message.info("没有可同步的真实账户");
      return;
    }
    setSyncingAll(true);
    let ok = 0;
    let failed = 0;
    // Sequential to avoid hitting exchange rate limits with many accounts.
    for (const acc of targets) {
      try {
        const res = await syncAccount.mutateAsync(acc.id);
        res.success ? (ok += 1) : (failed += 1);
      } catch {
        failed += 1;
      }
    }
    setSyncingAll(false);
    if (failed === 0) {
      message.success(`已同步 ${ok} 个账户`);
    } else {
      message.warning(`同步完成：成功 ${ok}，失败 ${failed}`);
    }
  };

  const onSync = async (id: number) => {
    try {
      const res = await syncAccount.mutateAsync(id);
      if (res.success) {
        message.success(`同步完成`);
      } else {
        message.warning(res.message ?? "同步失败");
      }
    } catch (e) {
      message.error((e as Error).message ?? "同步失败");
    }
  };

  const onDelete = async (id: number) => {
    try {
      await deleteAccount.mutateAsync(id);
      message.success("已删除");
    } catch (e) {
      message.error((e as Error).message ?? "删除失败");
    }
  };

  const columns = [
    {
      title: "账户",
      dataIndex: "account_name",
      render: (_: unknown, row: Account) => (
        <Space direction="vertical" size={2}>
          <Text strong>{row.account_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {exchangeMap.get(row.exchange_id) ?? `#${row.exchange_id}`} ·{" "}
            {ACCOUNT_TYPES.find((t) => t.value === row.account_type)?.label}
          </Text>
        </Space>
      ),
    },
    {
      title: "API Key",
      dataIndex: "api_key_masked",
      render: (v: string | null, row: Account) =>
        row.is_simulated ? (
          <Tag style={{ background: "#f1f5f9", border: "none", color: "#475569" }}>
            模拟账户
          </Tag>
        ) : (
          <span className="posi-mono" style={{ color: "var(--posi-text-secondary)" }}>
            {v ?? "—"}
          </span>
        ),
    },
    {
      title: "同步状态",
      dataIndex: "last_sync_status",
      render: (_: unknown, row: Account) => {
        const status: "ok" | "error" | "idle" =
          row.last_sync_status === "ok"
            ? "ok"
            : row.last_sync_status === "error"
            ? "error"
            : "idle";
        return (
          <Space direction="vertical" size={2}>
            <Space size={6}>
              <StatusDot status={status} />
              {row.last_sync_at ? (
                <RelativeTime
                  value={row.last_sync_at}
                  style={{ fontSize: 13 }}
                />
              ) : (
                <Text type="secondary" style={{ fontSize: 13 }}>
                  未同步
                </Text>
              )}
              {row.consecutive_failures > 0 && (
                <Tag color="red" style={{ margin: 0 }}>
                  失败 × {row.consecutive_failures}
                </Tag>
              )}
            </Space>
            {row.last_sync_status === "error" && row.last_sync_error && (
              <Tooltip title={row.last_sync_error}>
                <Text
                  type="danger"
                  style={{
                    fontSize: 12,
                    maxWidth: 260,
                    display: "inline-block",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {row.last_sync_error}
                </Text>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: "启用",
      dataIndex: "enabled",
      render: (v: boolean) => (
        <Tag
          color={v ? "blue" : "default"}
          style={{ margin: 0, border: "none" }}
        >
          {v ? "启用" : "停用"}
        </Tag>
      ),
    },
    {
      title: "操作",
      key: "actions",
      align: "right" as const,
      render: (_: unknown, row: Account) => (
        <Space>
          <Button
            size="small"
            icon={<SyncOutlined />}
            onClick={() => onSync(row.id)}
            loading={syncAccount.isPending && syncAccount.variables === row.id}
          >
            同步
          </Button>
          <Popconfirm
            title="确认删除该账户？"
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => onDelete(row.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="账户管理"
        description="只读 API Key 加密存储，支持模拟账户与多子账户"
        extra={
          <>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => accounts.refetch()}
            >
              刷新
            </Button>
            <Button
              icon={<SyncOutlined />}
              loading={syncingAll}
              onClick={onSyncAll}
            >
              全部同步
            </Button>
            <Button onClick={() => setExchangeModalOpen(true)}>
              新增交易所
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setDrawerOpen(true)}
            >
              新建账户
            </Button>
          </>
        }
      />

      <Card bodyStyle={{ padding: 0 }} style={{ borderRadius: 12 }}>
        <AsyncBoundary
          loading={accounts.isLoading}
          error={accounts.error}
          empty={!accounts.data?.length}
          emptyText="还没有账户，先创建一个吧"
        >
          <Table
            rowKey="id"
            columns={columns}
            dataSource={accounts.data ?? []}
            pagination={false}
            size={isMobile ? "small" : "middle"}
            scroll={isMobile ? { x: 920 } : undefined}
          />
        </AsyncBoundary>
      </Card>

      <Drawer
        title="新建账户"
        placement={isMobile ? "bottom" : "right"}
        height={isMobile ? "88%" : undefined}
        width={isMobile ? "100%" : 460}
        styles={
          isMobile
            ? { wrapper: { maxWidth: "100vw" }, body: { paddingBottom: 24 } }
            : undefined
        }
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        extra={
          <Button
            type="primary"
            onClick={onSubmit}
            loading={createAccount.isPending}
          >
            创建
          </Button>
        }
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            account_type: "spot",
            enabled: true,
            is_simulated: false,
          }}
        >
          <Form.Item
            label="交易所"
            name="exchange_id"
            rules={[{ required: true, message: "请选择交易所" }]}
          >
            <Select
              placeholder="请选择已配置的交易所"
              options={(exchanges.data ?? []).map((e) => ({
                value: e.id,
                label: e.name,
              }))}
            />
          </Form.Item>
          <Form.Item
            label="账户名称"
            name="account_name"
            rules={[{ required: true, message: "请输入账户名称" }]}
          >
            <Input placeholder="如：Binance 主账户" />
          </Form.Item>
          <Form.Item
            label="账户类型"
            name="account_type"
            rules={[{ required: true }]}
          >
            <Select options={ACCOUNT_TYPES} />
          </Form.Item>
          <Form.Item
            shouldUpdate={(p, n) => p.account_type !== n.account_type}
            noStyle
          >
            {({ getFieldValue }) => {
              const isSim = getFieldValue("account_type") === "simulated";
              if (isSim) {
                return (
                  <Tag
                    style={{
                      background: "#f1f5f9",
                      border: "none",
                      color: "#475569",
                      padding: "6px 10px",
                      marginBottom: 16,
                    }}
                  >
                    模拟账户无需 API Key，可在「手动录入」页写入快照
                  </Tag>
                );
              }
              return (
                <>
                  <Form.Item
                    label="API Key"
                    name="api_key"
                    rules={[{ required: true, message: "请输入只读 API Key" }]}
                  >
                    <Input.Password
                      autoComplete="off"
                      placeholder="只读权限的 API Key"
                    />
                  </Form.Item>
                  <Form.Item
                    label="API Secret"
                    name="api_secret"
                    rules={[{ required: true, message: "请输入 API Secret" }]}
                  >
                    <Input.Password autoComplete="off" />
                  </Form.Item>
                  <Form.Item label="Passphrase" name="passphrase">
                    <Input.Password
                      autoComplete="off"
                      placeholder="OKX/Bitget 等需要"
                    />
                  </Form.Item>
                </>
              );
            }}
          </Form.Item>
          <Form.Item label="启用同步" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Drawer>

      <Modal
        title="新增交易所"
        open={exchangeModalOpen}
        onCancel={() => setExchangeModalOpen(false)}
        onOk={onCreateExchange}
        confirmLoading={createExchange.isPending}
        okText="创建"
        cancelText="取消"
      >
        <Form form={exchangeForm} layout="vertical">
          <Form.Item
            label="交易所标识"
            name="name"
            rules={[{ required: true, message: "请输入 ccxt 标识" }]}
            extra="使用 ccxt 的 exchange id，如 binance / okx / bybit"
          >
            <Input placeholder="binance" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
