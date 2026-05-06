import { useMemo } from "react";
import { Layout, Menu, Space, Tooltip, Typography } from "antd";
import {
  AppstoreOutlined,
  BankOutlined,
  EditOutlined,
  LineChartOutlined,
  PieChartOutlined,
} from "@ant-design/icons";
import { Link, Outlet, useLocation } from "react-router-dom";
import { StatusDot } from "./StatusDot";
import { useOverview } from "@/api/hooks";
import { fmtRelative } from "@/utils/format";

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

const NAV = [
  { key: "/overview", label: "总览", icon: <AppstoreOutlined /> },
  { key: "/accounts", label: "账户", icon: <BankOutlined /> },
  { key: "/positions", label: "仓位", icon: <PieChartOutlined /> },
  { key: "/pnl", label: "盈亏", icon: <LineChartOutlined /> },
  { key: "/manual", label: "手动录入", icon: <EditOutlined /> },
];

export function AppLayout() {
  const location = useLocation();
  const overview = useOverview({ refetchInterval: 60_000 });

  const selected = useMemo(() => {
    const key = NAV.find((n) => location.pathname.startsWith(n.key))?.key;
    return key ?? "/overview";
  }, [location.pathname]);

  const status: "ok" | "error" | "idle" = overview.isError
    ? "error"
    : overview.data?.last_sync_at
    ? "ok"
    : "idle";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        width={220}
        theme="light"
        breakpoint="lg"
        collapsedWidth="64"
      >
        <div
          style={{
            height: 56,
            display: "flex",
            alignItems: "center",
            padding: "0 20px",
            borderBottom: "1px solid var(--posi-border)",
            gap: 10,
          }}
        >
          <span
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background:
                "linear-gradient(135deg, #1e3a8a 0%, #0ea5e9 100%)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#fff",
              fontWeight: 700,
              fontSize: 14,
              letterSpacing: "0.04em",
            }}
          >
            ph
          </span>
          <Text strong style={{ fontSize: 15, letterSpacing: "0.02em" }}>
            posihub
          </Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selected]}
          style={{ paddingTop: 12, border: "none" }}
          items={NAV.map((n) => ({
            key: n.key,
            icon: n.icon,
            label: <Link to={n.key}>{n.label}</Link>,
          }))}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Space size={16}>
            <Text
              style={{
                color: "var(--posi-text-muted)",
                fontSize: 12,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              Trading Account &amp; Position Hub
            </Text>
          </Space>
          <Space size={20}>
            <Tooltip
              title={
                overview.data?.last_sync_at
                  ? `上次同步 ${fmtRelative(overview.data.last_sync_at)}`
                  : "暂无同步记录"
              }
            >
              <StatusDot
                status={status}
                label={
                  status === "error"
                    ? "API 异常"
                    : status === "ok"
                    ? "已连接"
                    : "等待同步"
                }
              />
            </Tooltip>
          </Space>
        </Header>
        <Content
          style={{
            padding: 24,
            maxWidth: 1440,
            width: "100%",
            margin: "0 auto",
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
