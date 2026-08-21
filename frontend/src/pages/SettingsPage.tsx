import {
  Button,
  Card,
  Descriptions,
  Segmented,
  Space,
  Tag,
  Table,
  Tooltip,
  Typography,
  message,
} from "antd";
import { Link } from "react-router-dom";
import {
  ApiOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { PageHeader } from "@/components/PageHeader";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { StatusDot } from "@/components/StatusDot";
import { useState } from "react";
import {
  useExchangeConnections,
  useHealth,
  useOverview,
  useRunDailySnapshot,
  useTestExchangeConnection,
} from "@/api/hooks";
import { useLocale } from "@/i18n/LocaleContext";
import type { ExchangeConnection } from "@/api/types";

const { Text, Paragraph } = Typography;

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

/** Shown as reference; actual interval is configured in backend `.env`. */
const DEFAULT_SYNC_INTERVAL_MINUTES = 5;
const DEFAULT_SNAPSHOT_TIME = "23:55";
const DEFAULT_TIMEZONE = "Asia/Shanghai";

export function SettingsPage() {
  const { locale, setLocale, t } = useLocale();
  const health = useHealth();
  const overview = useOverview();
  const connections = useExchangeConnections();
  const runSnapshot = useRunDailySnapshot();
  const testConnection = useTestExchangeConnection();
  const [testingAll, setTestingAll] = useState(false);
  const apiDisplay = API_BASE || t("settings.apiDisplayDev");

  const onRunSnapshot = async () => {
    try {
      const res = await runSnapshot.mutateAsync();
      message.success(
        t("settings.snapshotCreated", {
          accounts: res.accounts_written,
          positions: res.positions_written,
        })
      );
    } catch (e) {
      message.error((e as Error).message ?? t("settings.snapshotFailed"));
    }
  };

  const backendOk = health.isSuccess && health.data?.status === "ok";
  const dateLocale = locale === "zh-CN" ? "zh-CN" : "en-US";

  const statusLabel = (value: ExchangeConnection["status"]) => {
    switch (value) {
      case "connected":
        return t("settings.connected");
      case "error":
        return t("settings.connectionFailed");
      case "not_configured":
        return t("settings.notConfigured");
      case "simulated":
        return t("settings.simulated");
      default:
        return t("settings.notTested");
    }
  };

  const onTestConnection = async (accountId: number) => {
    try {
      const result = await testConnection.mutateAsync(accountId);
      if (result.status === "connected") {
        message.success(t("settings.testSuccess"));
      } else if (result.status === "error") {
        message.error(result.message ?? t("settings.testFailed"));
      }
    } catch (e) {
      message.error((e as Error).message ?? t("settings.testFailed"));
    }
  };

  const onTestAllConnections = async () => {
    const targets = (connections.data ?? []).filter(
      (row) => !row.is_simulated && row.status !== "not_configured"
    );
    if (!targets.length) {
      message.info(t("settings.noExchangeConnections"));
      return;
    }

    setTestingAll(true);
    let succeeded = 0;
    let failed = 0;
    for (const row of targets) {
      try {
        const result = await testConnection.mutateAsync(row.account_id);
        result.status === "connected" ? (succeeded += 1) : (failed += 1);
      } catch {
        failed += 1;
      }
    }
    setTestingAll(false);
    if (failed === 0) {
      message.success(`${t("settings.testSuccess")} · ${succeeded}`);
    } else {
      message.warning(`${t("settings.testFailed")} · ${failed}`);
    }
  };

  const connectionColumns = [
    {
      title: t("settings.exchange"),
      dataIndex: "exchange_name",
      render: (_: unknown, row: ExchangeConnection) => (
        <Space direction="vertical" size={2}>
          <Text strong>{row.exchange_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.account_type}
          </Text>
        </Space>
      ),
    },
    {
      title: t("settings.account"),
      dataIndex: "account_name",
      render: (value: string, row: ExchangeConnection) => (
        <Space direction="vertical" size={2}>
          <Text>{value}</Text>
          {!row.enabled && <Tag>{t("settings.notTested")}</Tag>}
        </Space>
      ),
    },
    {
      title: t("settings.credentials"),
      dataIndex: "api_key_masked",
      render: (value: string | null, row: ExchangeConnection) =>
        row.is_simulated ? (
          <Tag>{t("settings.simulated")}</Tag>
        ) : (
          <Text code>{value ?? t("settings.notConfigured")}</Text>
        ),
    },
    {
      title: t("settings.status"),
      dataIndex: "status",
      render: (value: ExchangeConnection["status"], row: ExchangeConnection) => {
        const dotStatus = value === "connected" ? "ok" : value === "error" ? "error" : "idle";
        return (
          <Space direction="vertical" size={2}>
            <StatusDot status={dotStatus} label={statusLabel(value)} />
            {row.message && value === "error" && (
              <Tooltip title={row.message}>
                <Text
                  type="danger"
                  style={{
                    display: "inline-block",
                    maxWidth: 260,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    fontSize: 12,
                  }}
                >
                  {row.message}
                </Text>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: t("settings.lastTest"),
      dataIndex: "last_test_at",
      render: (value: string | null, row: ExchangeConnection) => (
        <Space direction="vertical" size={2}>
          <Text type="secondary">
            {value ? new Date(value).toLocaleString(dateLocale) : t("common.dash")}
          </Text>
          {row.latency_ms !== null && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("settings.latency")}: {row.latency_ms} ms
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: "",
      key: "actions",
      align: "right" as const,
      render: (_: unknown, row: ExchangeConnection) => (
        <Button
          size="small"
          icon={<ApiOutlined />}
          disabled={row.is_simulated || row.status === "not_configured"}
          loading={
            testConnection.isPending && testConnection.variables === row.account_id
          }
          onClick={() => onTestConnection(row.account_id)}
        >
          {t("settings.testApi")}
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title={t("settings.title")}
        description={t("settings.description")}
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={health.isFetching}
            onClick={() => health.refetch()}
          >
            {t("settings.checkConnection")}
          </Button>
        }
      />

      <Card title={t("locale.label")} style={{ borderRadius: 12 }}>
        <Segmented
          value={locale}
          onChange={(value) => setLocale(value as typeof locale)}
          options={[
            { label: t("locale.chinese"), value: "zh-CN" },
            { label: t("locale.english"), value: "en" },
          ]}
        />
      </Card>

      <Card title={t("settings.frontend")} style={{ borderRadius: 12 }}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label={t("settings.app")}>
            posihub frontend v
            {import.meta.env.MODE === "development" ? "dev" : "prod"}
          </Descriptions.Item>
          <Descriptions.Item label={t("settings.apiBase")}>
            <Text code copyable={!!API_BASE}>
              {apiDisplay}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label={t("settings.buildMode")}>
            <Tag>{import.meta.env.MODE}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t("settings.cache")}>
            {t("settings.cacheValue")}
          </Descriptions.Item>
        </Descriptions>
        <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          {t("settings.deployHint", {
            env: "VITE_API_BASE_URL",
            api: "/api",
            health: "/health",
          })}
        </Paragraph>
      </Card>

      <Card title={t("settings.backend")} style={{ borderRadius: 12 }}>
        <AsyncBoundary
          loading={health.isLoading}
          error={health.error}
          empty={false}
        >
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Space size={8}>
              <StatusDot status={backendOk ? "ok" : "error"} />
              <Text>
                {backendOk
                  ? t("settings.backendOnline")
                  : health.isError
                    ? t("settings.backendOffline")
                    : t("settings.backendUnknown")}
              </Text>
              {health.data?.version && (
                <Tag icon={<ApiOutlined />}>v{health.data.version}</Tag>
              )}
            </Space>
            {health.data && (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label={t("settings.serviceName")}>
                  {health.data.app}
                </Descriptions.Item>
                <Descriptions.Item label={t("settings.status")}>
                  {health.data.status}
                </Descriptions.Item>
                <Descriptions.Item label={t("settings.version")}>
                  {health.data.version}
                </Descriptions.Item>
              </Descriptions>
            )}
          </Space>
        </AsyncBoundary>
      </Card>

      <Card
        title={t("settings.exchangeConnections")}
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={connections.isFetching || testingAll}
            onClick={onTestAllConnections}
          >
            {t("settings.testAllApis")}
          </Button>
        }
        style={{ borderRadius: 12 }}
      >
        <Paragraph type="secondary" style={{ marginTop: 0 }}>
          {t("settings.exchangeConnectionsDescription")}
        </Paragraph>
        <AsyncBoundary
          loading={connections.isLoading}
          error={connections.error}
          empty={!connections.data?.length}
          emptyText={t("settings.noExchangeConnections")}
        >
          <Table<ExchangeConnection>
            rowKey="account_id"
            columns={connectionColumns}
            dataSource={connections.data ?? []}
            loading={connections.isFetching && !connections.isLoading}
            pagination={false}
            size="small"
            scroll={{ x: 920 }}
          />
        </AsyncBoundary>
      </Card>

      <Card title={t("settings.scheduler")} style={{ borderRadius: 12 }}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label={t("settings.accountSyncInterval")}>
            {t("settings.defaultEveryMinutes", {
              minutes: DEFAULT_SYNC_INTERVAL_MINUTES,
            })}{" "}
            (<Text code>SYNC_INTERVAL_MINUTES</Text>)
          </Descriptions.Item>
          <Descriptions.Item label={t("settings.dailySnapshotTime")}>
            {DEFAULT_SNAPSHOT_TIME} {DEFAULT_TIMEZONE} (
            <Text code>DAILY_SNAPSHOT_TIME</Text>)
          </Descriptions.Item>
          <Descriptions.Item label={t("settings.latestSync")}>
            {overview.data?.last_sync_at
              ? new Date(overview.data.last_sync_at).toLocaleString(dateLocale)
              : t("common.dash")}
          </Descriptions.Item>
          <Descriptions.Item label={t("settings.latestSnapshot")}>
            {overview.data?.last_snapshot_at
              ? new Date(overview.data.last_snapshot_at).toLocaleString(dateLocale)
              : t("common.dash")}
          </Descriptions.Item>
        </Descriptions>
        <Space style={{ marginTop: 16 }} wrap>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={runSnapshot.isPending}
            onClick={onRunSnapshot}
          >
            {t("settings.runSnapshot")}
          </Button>
          <Link to="/snapshots">
            <Button>{t("settings.viewSnapshots")}</Button>
          </Link>
          <Link to="/manual">
            <Button>{t("settings.manualEntry")}</Button>
          </Link>
        </Space>
      </Card>

      <Card title={t("settings.quickLinks")} style={{ borderRadius: 12 }}>
        <Space wrap>
          <Link to="/accounts">
            <Button>{t("settings.accountManagement")}</Button>
          </Link>
          <Link to="/symbols">
            <Button>{t("settings.symbols")}</Button>
          </Link>
          <Link to="/positions">
            <Button>{t("settings.positions")}</Button>
          </Link>
        </Space>
      </Card>
    </Space>
  );
}
