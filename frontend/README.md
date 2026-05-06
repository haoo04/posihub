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

## 依赖

- `react`, `react-dom`, `react-router-dom`
- `antd`, `@ant-design/icons`
- `@tanstack/react-query`
- `axios`, `dayjs`
- `echarts`, `echarts-for-react`
