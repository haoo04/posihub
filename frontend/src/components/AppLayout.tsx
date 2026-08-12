import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Drawer,
  Grid,
  Layout,
  Menu,
  Segmented,
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
import { useLocale } from "@/i18n/LocaleContext";

const { useBreakpoint } = Grid;

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { locale, setLocale, t } = useLocale();
  const overview = useOverview({ refetchInterval: 60_000 });
  const screens = useBreakpoint();
  const mdUp = !!screens.md;
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const navItems = useMemo(
    () => [
      { key: "/overview", label: t("nav.overview"), icon: <AppstoreOutlined /> },
      { key: "/accounts", label: t("nav.accounts"), icon: <BankOutlined /> },
      { key: "/positions", label: t("nav.positions"), icon: <PieChartOutlined /> },
      { key: "/pnl", label: t("nav.pnl"), icon: <LineChartOutlined /> },
      { key: "/performance", label: t("nav.performance"), icon: <FundOutlined /> },
      { key: "/snapshots", label: t("nav.snapshots"), icon: <HistoryOutlined /> },
      { key: "/symbols", label: t("nav.symbols"), icon: <TagsOutlined /> },
      { key: "/manual", label: t("nav.manual"), icon: <EditOutlined /> },
      { key: "/settings", label: t("nav.settings"), icon: <SettingOutlined /> },
    ],
    [t]
  );

  const selected = useMemo(() => {
    const key = navItems.find((n) => location.pathname.startsWith(n.key))?.key;
    return key ?? "/overview";
  }, [location.pathname, navItems]);

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
          ? navItems.map((n) => ({
              key: n.key,
              icon: n.icon,
              label: <Link to={n.key}>{n.label}</Link>,
            }))
          : navItems.map((n) => ({
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
                aria-label={t("nav.openMenu")}
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
              {mdUp ? t("layout.desktopSubtitle") : "posihub"}
            </Text>
          </Space>
          <Space size={mdUp ? 20 : 8}>
            <Segmented
              size="small"
              value={locale}
              onChange={(value) => setLocale(value as typeof locale)}
              options={[
                { label: "中文", value: "zh-CN" },
                { label: "EN", value: "en" },
              ]}
              aria-label={t("locale.label")}
            />
            <Tooltip
              title={
                overview.data?.last_sync_at
                  ? t("layout.lastSync", {
                      time: fmtRelative(overview.data.last_sync_at),
                    })
                  : t("layout.noSyncRecord")
              }
            >
              <StatusDot
                status={status}
                label={
                  mdUp
                    ? status === "error"
                      ? t("layout.apiError")
                      : status === "ok"
                        ? t("layout.connected")
                        : t("layout.waitingSync")
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
