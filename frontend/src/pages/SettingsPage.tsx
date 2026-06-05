import {
  Button,
  Card,
  Descriptions,
  Space,
  Tag,
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
import { useHealth, useOverview, useRunDailySnapshot } from "@/api/hooks";

const { Text, Paragraph } = Typography;

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const API_DISPLAY = API_BASE || "（开发代理 → http://127.0.0.1:8000）";

/** Shown as reference; actual interval is configured in backend `.env`. */
const DEFAULT_SYNC_INTERVAL_MINUTES = 5;
const DEFAULT_SNAPSHOT_TIME = "23:55";
const DEFAULT_TIMEZONE = "Asia/Shanghai";

export function SettingsPage() {
  const health = useHealth();
  const overview = useOverview();
  const runSnapshot = useRunDailySnapshot();

  const onRunSnapshot = async () => {
    try {
      const res = await runSnapshot.mutateAsync();
      message.success(
        `快照已生成：账户 ${res.accounts_written}，仓位 ${res.positions_written}`
      );
    } catch (e) {
      message.error((e as Error).message ?? "触发失败");
    }
  };

  const backendOk = health.isSuccess && health.data?.status === "ok";

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="设置"
        description="运行环境、后端连接与常用维护操作"
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={health.isFetching}
            onClick={() => health.refetch()}
          >
            检测连接
          </Button>
        }
      />

      <Card title="前端" style={{ borderRadius: 12 }}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label="应用">
            posihub frontend v{import.meta.env.MODE === "development" ? "dev" : "prod"}
          </Descriptions.Item>
          <Descriptions.Item label="API 基址">
            <Text code copyable={!!API_BASE}>
              {API_DISPLAY}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label="构建模式">
            <Tag>{import.meta.env.MODE}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="数据缓存">
            React Query staleTime 30s（全局默认）
          </Descriptions.Item>
        </Descriptions>
        <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          生产部署时在构建前设置环境变量{" "}
          <Text code>VITE_API_BASE_URL</Text> 指向后端地址；本地开发可留空，由
          Vite 代理 <Text code>/api</Text> 与 <Text code>/health</Text>。
        </Paragraph>
      </Card>

      <Card title="后端连接" style={{ borderRadius: 12 }}>
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
                  ? "后端在线"
                  : health.isError
                    ? "无法连接后端"
                    : "状态未知"}
              </Text>
              {health.data?.version && (
                <Tag icon={<ApiOutlined />}>v{health.data.version}</Tag>
              )}
            </Space>
            {health.data && (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="服务名">
                  {health.data.app}
                </Descriptions.Item>
                <Descriptions.Item label="状态">
                  {health.data.status}
                </Descriptions.Item>
                <Descriptions.Item label="版本">
                  {health.data.version}
                </Descriptions.Item>
              </Descriptions>
            )}
          </Space>
        </AsyncBoundary>
      </Card>

      <Card title="调度与快照（后端 .env 配置）" style={{ borderRadius: 12 }}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label="账户同步间隔">
            默认每 {DEFAULT_SYNC_INTERVAL_MINUTES} 分钟（
            <Text code>SYNC_INTERVAL_MINUTES</Text>）
          </Descriptions.Item>
          <Descriptions.Item label="每日快照时间">
            {DEFAULT_SNAPSHOT_TIME} {DEFAULT_TIMEZONE}（
            <Text code>DAILY_SNAPSHOT_TIME</Text>）
          </Descriptions.Item>
          <Descriptions.Item label="最近同步">
            {overview.data?.last_sync_at
              ? new Date(overview.data.last_sync_at).toLocaleString("zh-CN")
              : "—"}
          </Descriptions.Item>
          <Descriptions.Item label="最近快照">
            {overview.data?.last_snapshot_at
              ? new Date(overview.data.last_snapshot_at).toLocaleString("zh-CN")
              : "—"}
          </Descriptions.Item>
        </Descriptions>
        <Space style={{ marginTop: 16 }} wrap>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={runSnapshot.isPending}
            onClick={onRunSnapshot}
          >
            立即生成每日快照
          </Button>
          <Link to="/snapshots">
            <Button>查看历史快照</Button>
          </Link>
          <Link to="/manual">
            <Button>手动录入</Button>
          </Link>
        </Space>
      </Card>

      <Card title="快捷入口" style={{ borderRadius: 12 }}>
        <Space wrap>
          <Link to="/accounts">
            <Button>账户管理</Button>
          </Link>
          <Link to="/symbols">
            <Button>Symbol 映射</Button>
          </Link>
          <Link to="/positions">
            <Button>仓位</Button>
          </Link>
        </Space>
      </Card>
    </Space>
  );
}
