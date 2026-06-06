import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Drawer,
  Grid,
  Layout,
  Menu,
  Space,
  Tooltip,
  Typography,
} from "antd";
import {
  AppstoreOutlined,
  BankOutlined,
  EditOutlined,
  HistoryOutlined,
  FundOutlined,
  LineChartOutlined,
  MenuOutlined,
  PieChartOutlined,
  SettingOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { StatusDot } from "./StatusDot";
import { useOverview } from "@/api/hooks";
import { fmtRelative } from "@/utils/format";

const { useBreakpoint } = Grid;

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

const NAV = [
  { key: "/overview", label: "总览", icon: <AppstoreOutlined /> },
  { key: "/accounts", label: "账户", icon: <BankOutlined /> },
  { key: "/positions", label: "仓位", icon: <PieChartOutlined /> },
  { key: "/pnl", label: "盈亏", icon: <LineChartOutlined /> },
  { key: "/performance", label: "交易表现", icon: <FundOutlined /> },
  { key: "/snapshots", label: "历史快照", icon: <HistoryOutlined /> },
  { key: "/symbols", label: "Symbol 映射", icon: <TagsOutlined /> },
  { key: "/manual", label: "手动录入", icon: <EditOutlined /> },
  { key: "/settings", label: "设置", icon: <SettingOutlined /> },
];

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const overview = useOverview({ refetchInterval: 60_000 });
  const screens = useBreakpoint();
  const mdUp = !!screens.md;
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const selected = useMemo(() => {
    const key = NAV.find((n) => location.pathname.startsWith(n.key))?.key;
    return key ?? "/overview";
  }, [location.pathname]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  const status: "ok" | "error" | "idle" = overview.isError
    ? "error"
    : overview.data?.last_sync_at
      ? "ok"
      : "idle";

  const navMenu = (
    <Menu
      mode="inline"
      selectedKeys={[selected]}
      style={{ paddingTop: mdUp ? 12 : 0, border: "none" }}
      items={
        mdUp
          ? NAV.map((n) => ({
              key: n.key,
              icon: n.icon,
              label: <Link to={n.key}>{n.label}</Link>,
            }))
          : NAV.map((n) => ({
              key: n.key,
              icon: n.icon,
              label: n.label,
              onClick: () => {
                navigate(n.key);
                setMobileNavOpen(false);
              },
            }))
      }
    />
  );

  return (
    <Layout style={{ minHeight: "100vh" }}>
      {mdUp ? (
        <Sider
          width={220}
          theme="light"
          breakpoint="lg"
          collapsedWidth={64}
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
          {navMenu}
        </Sider>
      ) : null}

      <Layout>
        <Header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            paddingInline: mdUp ? undefined : 12,
          }}
        >
          <Space size={12}>
            {!mdUp ? (
              <Button
                type="text"
                icon={<MenuOutlined style={{ fontSize: 18 }} />}
                onClick={() => setMobileNavOpen(true)}
                aria-label="打开导航菜单"
                style={{ marginLeft: -8 }}
              />
            ) : null}
            <Text
              style={{
                color: "var(--posi-text-muted)",
                fontSize: mdUp ? 12 : 11,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: mdUp ? "none" : "42vw",
              }}
            >
              {mdUp ? "Trading Account & Position Hub" : "posihub"}
            </Text>
          </Space>
          <Space size={mdUp ? 20 : 8}>
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
                  mdUp
                    ? status === "error"
                      ? "API 异常"
                      : status === "ok"
                        ? "已连接"
                        : "等待同步"
                    : undefined
                }
              />
            </Tooltip>
          </Space>
        </Header>

        {!mdUp ? (
          <Drawer
            title={
              <Space align="center">
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
                    fontSize: 13,
                  }}
                >
                  ph
                </span>
                <Text strong>posihub</Text>
              </Space>
            }
            placement="left"
            width={280}
            open={mobileNavOpen}
            onClose={() => setMobileNavOpen(false)}
            styles={{ body: { padding: 0 } }}
            destroyOnClose={false}
          >
            {navMenu}
          </Drawer>
        ) : null}

        <Content className="posi-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
