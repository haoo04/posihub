# posihub frontend

React + Vite + TypeScript + Ant Design 5 实现的 posihub 前端，采用「高级浅色金融风」主题。

## 启动

```powershell
cd frontend
npm install
npm run dev   # http://127.0.0.1:5173
```

> 默认会代理 `/api` 与 `/health` 到后端 `http://127.0.0.1:8000`，可通过 `VITE_API_BASE_URL` 覆盖。

## 构建

```powershell
npm run build       # tsc + vite build
npm run preview     # 预览构建产物
```

## 视觉规范

- 主色 `#1e3a8a`（深海军蓝），强调色 `#0ea5e9`
- 涨绿 `#16a34a`，跌红 `#dc2626`，全部使用柔和的金融配色
- 数字与价格统一使用 `JetBrains Mono` 等宽字体 + tabular figures
- 全局通过 AntD `ConfigProvider` 注入 design tokens；图表统一使用 `posi-light` ECharts 主题

## 页面结构

| 路径 | 说明 |
| --- | --- |
| `/overview` | KPI 卡片 + 权益走势 + 持仓占比 + 主要持仓表 |
| `/accounts` | 账户与交易所管理（创建、删除、单账户同步） |
| `/positions` | `split` / `merged` 双视图，支持搜索 |
| `/pnl` | 区间切换 + 权益曲线 + 未实现盈亏柱 |
| `/manual` | 手动快照录入（基础信息 / 余额 / 仓位） |

## 移动端适配（&lt;768px）

- **导航**：侧边栏收起为 **左侧 Drawer**，顶栏 **汉堡菜单** 打开导航；路由切换后自动关闭抽屉。
- **主内容**：减小内边距、支持 **safe-area** 底部留白（刘海屏 / 全面屏）。
- **宽表格**：账户 / 仓位表启用 **横向滚动**；自定义表格外包 `.posi-table-wrap`。
- **表单**：「新建账户」在手机上为 **底部抽屉**（高度约 88%），便于单手操作。
- **图表**：总览 / 盈亏在窄屏下略降高度、饼图半径与柱状宽度收紧。
- **分段器**：`Segmented` 使用 `block` 占满宽度，便于点选。
- **页头**：标题与工具按钮 **纵向堆叠**，`extra` 内 Fragment 会被展平以便按钮换行。

## 依赖

- `react`, `react-dom`, `react-router-dom`
- `antd`, `@ant-design/icons`
- `@tanstack/react-query`
- `axios`, `dayjs`
- `echarts`, `echarts-for-react`
