import type { ThemeConfig } from "antd";

/**
 * Premium light financial theme.
 *
 * - Deep navy primary, sky-blue accent.
 * - Generous radius and a quieter neutral palette than AntD defaults.
 * - All numeric content uses JetBrains Mono via global CSS.
 */
export const antdTheme: ThemeConfig = {
  cssVar: true,
  hashed: false,
  token: {
    colorPrimary: "#1e3a8a",
    colorInfo: "#0ea5e9",
    colorSuccess: "#16a34a",
    colorError: "#dc2626",
    colorWarning: "#d97706",

    colorTextBase: "#0f172a",
    colorTextSecondary: "#475569",
    colorTextTertiary: "#94a3b8",
    colorTextDescription: "#64748b",

    colorBgBase: "#ffffff",
    colorBgLayout: "#f6f7fb",
    colorBgContainer: "#ffffff",
    colorBgElevated: "#ffffff",

    colorBorder: "#e6e8ef",
    colorBorderSecondary: "#eef0f5",

    fontFamily:
      '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
    fontSize: 14,
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,
    wireframe: false,
    motionDurationMid: "0.18s",
  },
  components: {
    Layout: {
      headerBg: "#ffffff",
      siderBg: "#ffffff",
      bodyBg: "#f6f7fb",
      headerHeight: 56,
      headerPadding: "0 24px",
    },
    Menu: {
      itemBg: "transparent",
      itemSelectedBg: "#e8edfb",
      itemSelectedColor: "#1e3a8a",
      itemHoverBg: "#f1f3f9",
      itemHeight: 40,
      iconSize: 16,
    },
    Card: {
      headerBg: "transparent",
      paddingLG: 20,
    },
    Button: {
      controlHeight: 36,
      fontWeight: 500,
    },
    Table: {
      headerBg: "#fafbfd",
      headerColor: "#475569",
      rowHoverBg: "#fafbfd",
      borderColor: "#e6e8ef",
      cellPaddingBlock: 12,
    },
    Tabs: {
      itemColor: "#64748b",
      itemSelectedColor: "#1e3a8a",
      itemActiveColor: "#1e3a8a",
      inkBarColor: "#1e3a8a",
    },
    Tag: {
      defaultBg: "#f1f3f9",
      defaultColor: "#475569",
    },
    Statistic: {
      titleFontSize: 12,
    },
  },
};
