# posihub frontend

[简体中文](README.md) | [English](README.en.md) | [项目总览](../README.md)

posihub 前端是一个使用 React 18、TypeScript、Vite 5、Ant Design 5、TanStack Query 和 ECharts 构建的响应式交易账户与仓位看板。

## 当前页面

| 路径 | 功能 |
| --- | --- |
| `/overview` | 总权益、未实现/已实现盈亏、仓位数量、权益走势、持仓占比和主要持仓 |
| `/accounts` | 新增交易所与真实/模拟账户，单账户或全部同步，删除账户，预览并提交 Bitget 历史回填 |
| `/positions` | 现货/合约与分仓/合仓视图、搜索、15 秒公开行情刷新、订单批次和本地平仓核算 |
| `/pnl` | 7/30/90/365 日权益与未实现盈亏图表 |
| `/performance` | 账户筛选、权益/回撤、胜率、Profit Factor、Calmar、维度分析和可导出的平仓明细 |
| `/snapshots` | 按日期与账户查询账户/仓位快照、立即生成快照、导出 CSV |
| `/symbols` | 搜索、筛选、启停、编辑、删除和导出 Symbol 映射 |
| `/manual` | 手动补录账户、余额和仓位快照，适用于模拟账户或历史数据 |
| `/settings` | 切换语言、检查后端健康状态、测试交易所 API、触发快照和访问维护入口 |

仓位页的 FIFO/指定批次平仓只更新 posihub 的本地记账数据，不会向交易所提交订单。

## 本地开发

### 环境要求

- Node.js 18+
- npm
- 正在运行的 posihub 后端（默认 `http://127.0.0.1:8000`）

### 安装与启动

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

打开 <http://127.0.0.1:5173>。

默认不需要创建前端 `.env`：浏览器请求使用同源路径，Vite 会将 `/api` 和 `/health` 代理到 `http://127.0.0.1:8000`。

如需让浏览器直接请求其他 API 地址，可复制示例并修改：

```powershell
Copy-Item .env.example .env
```

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

设置该变量后，请确保后端的 `CORS_ALLOW_ORIGINS` 包含前端来源。生产构建中的 `VITE_*` 值会写入静态资源；这里只应配置公开的 API 地址，不能存放密钥。

完整的前后端安装与一键启动方式见[根目录 README](../README.md)。

## 可用脚本

| 命令 | 说明 |
| --- | --- |
| `npm.cmd run dev` | 启动 Vite 开发服务器（`127.0.0.1:5173`） |
| `npm.cmd run build` | 执行 TypeScript project build 并生成生产资源 |
| `npm.cmd run preview` | 本地预览生产构建 |
| `npm.cmd run test` | 运行一次 Vitest 测试 |
| `npm.cmd run test:watch` | 以 watch 模式运行 Vitest |
| `npm.cmd run lint` | 对 TypeScript/TSX 运行 ESLint；当前依赖未固定 ESLint，需在环境中另行提供 |

在 macOS 或 Linux 上将 `npm.cmd` 替换为 `npm`。

## 数据获取行为

- `src/api/client.ts` 创建 Axios 客户端，并把后端 `detail` 作为可展示的错误信息。
- TanStack Query 的全局 `staleTime` 为 30 秒，默认不在窗口聚焦时刷新。
- 账户列表会在应用启动时预取，供仓位和手动录入页面解析账户名称。
- 仓位行情使用单独策略：10 秒 stale time、页面可见时每 15 秒轮询、窗口重新聚焦时刷新。
- 实时行情只覆盖当前页面的价格与合仓名义价值；失败时保留查询缓存或后端仓位价格，不写入数据库。

## 国际化

前端使用轻量的 `LocaleContext` 和类型化消息对象，不依赖额外 i18n 库：

- 支持 `zh-CN` 和 `en`，默认语言为简体中文；
- 选择保存在浏览器 `localStorage` 的 `posihub-locale`；
- 切换时同步 Ant Design locale、dayjs 日期格式、`document.documentElement.lang` 和标题；
- 找不到英文消息时回退到简体中文。

当前已翻译应用导航与状态、通用异步状态、总览页和设置页。账户、仓位、盈亏、交易表现、快照、Symbol 映射与手动录入页仍以中文业务文案为主。

## 响应式与视觉规范

- `<768px` 时侧边栏变为左侧 Drawer，路由切换后自动关闭。
- 页面操作、筛选器和表单在窄屏下纵向排列，宽表格启用横向滚动或卡片视图。
- “新建账户”在移动端使用底部 Drawer；图表、分段器和页面内边距会按断点调整。
- Ant Design token 和 `posi-light` ECharts 主题统一使用海军蓝主色、天蓝强调色、涨绿和跌红。
- 数字与价格使用等宽字体回退和 tabular figures，保持列对齐。

## 代码结构

```text
frontend/
├─ src/
│  ├─ api/          # Axios 客户端、React Query hooks、API 类型
│  ├─ components/   # 布局、表格、弹窗和通用展示组件
│  ├─ hooks/        # 响应式 hooks
│  ├─ i18n/         # LocaleContext 与中英文消息
│  ├─ pages/        # 路由页面
│  ├─ styles/       # 全局样式和移动端规则
│  ├─ theme/        # Ant Design 与 ECharts 主题
│  ├─ utils/        # 格式化、CSV 和订单计算工具
│  ├─ App.tsx       # 路由表
│  └─ main.tsx      # React providers 与应用入口
├─ .env.example
├─ package.json
└─ vite.config.ts
```

## 验证

```powershell
Set-Location frontend
npm.cmd run test
npm.cmd run build
```
