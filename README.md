# posihub

[简体中文](README.md) | [English](README.en.md)

posihub 是一个本地优先的个人多交易所账户、仓位、盈亏与交易表现管理系统。后端使用 FastAPI、SQLModel、SQLite 和 CCXT，前端使用 React、TypeScript、Vite、Ant Design 与 ECharts。

> posihub 用于只读同步、资产展示和本地交易记账，不会向交易所提交订单、撤单或提现请求。

## 功能概览

- **账户与交易所**：管理现货、U 本位永续、币本位永续、交割合约、资金和模拟账户；API 凭据加密存储；支持单账户/全部账户同步及定时同步。
- **连接状态**：通过只读余额接口测试交易所 API，记录连接状态、延迟和脱敏后的错误信息。
- **仓位与行情**：在现货/合约、分仓/合仓视图间切换；按统一 Symbol 聚合仓位；仓位页每 15 秒获取一次公开行情，失败时保留最近可用价格。
- **订单与本地核算**：记录仓位订单批次，支持 FIFO 或指定批次的本地平仓核算，并计算已实现/未实现盈亏；这些操作不会在交易所执行交易。
- **历史回填**：Bitget 账户支持“预览后提交”的历史订单回填、去重、冲突检查与盈亏校验。
- **快照与分析**：自动或手动生成账户/仓位日快照，查看权益与盈亏曲线、回撤、胜率、Profit Factor、Calmar 比率、连续盈亏及多维度表现。
- **数据维护**：管理 Symbol 映射、录入模拟/历史快照，并从快照、Symbol 映射和交易明细页面导出 CSV。
- **界面体验**：响应式桌面/移动端布局；应用导航、总览和设置页支持简体中文/英文切换。

交易所使用 CCXT exchange id 配置。内置 Symbol 种子主要覆盖 Binance、Bybit、Bitget 和 OKX；历史订单 API 回填目前仅支持 Bitget。

## 技术栈

| 层 | 主要技术 |
| --- | --- |
| 后端 | Python 3.12+、FastAPI 0.115、Pydantic 2、SQLModel / SQLAlchemy |
| 交易所与任务 | CCXT 4.5、APScheduler 3.10 |
| 数据与安全 | SQLite、Fernet 加密（`cryptography`） |
| 前端 | React 18、TypeScript 5.6、Vite 5、Ant Design 5 |
| 数据请求与图表 | TanStack Query 5、Axios、ECharts 5 |
| 测试 | pytest、Vitest |

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+ 与 npm
- PowerShell 7（以下示例使用 PowerShell）

在 macOS 或 Linux 上可将示例中的 `npm.cmd` 替换为 `npm`。

### 1. 安装依赖

在项目根目录执行：

```powershell
python -m pip install -r backend/requirements.txt
npm.cmd install
npm.cmd --prefix frontend install
```

根目录的 Node.js 依赖只用于同时启动前后端；前端依赖安装在 `frontend/`。

### 2. 配置环境

```powershell
Copy-Item .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将生成的密钥写入根目录 `.env`：

```dotenv
POSIHUB_ENCRYPTION_KEY=粘贴生成的密钥
```

该密钥用于加密交易所凭据。请保管好现有密钥；更换或丢失后，已存储的凭据将无法解密。

### 3. 初始化本地数据

```powershell
python -m scripts.init_db
python -m scripts.seed_symbol_mapping
```

两个命令都可以重复执行。后端启动时也会自动创建缺失的数据表；种子脚本用于写入常用交易所 Symbol 映射。

### 4. 启动完整应用

```powershell
npm.cmd run dev
```

- 前端：<http://127.0.0.1:5173>
- API：<http://127.0.0.1:8000>
- OpenAPI：<http://127.0.0.1:8000/docs>

也可以在两个终端中分别启动：

```powershell
# 终端 1
Set-Location backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 终端 2
Set-Location frontend
npm.cmd run dev
```

## 主要配置

后端从项目根目录的 `.env` 读取配置。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./posihub.db` | 相对 SQLite 路径按 `backend/` 解析 |
| `POSIHUB_ENCRYPTION_KEY` | 空 | 凭据加密密钥；为空时后台调度器不会启动 |
| `APP_TIMEZONE` | `Asia/Shanghai` | 定时任务时区 |
| `SYNC_INTERVAL_MINUTES` | `5` | 自动同步间隔 |
| `SYNC_MAX_WORKERS` | `4` | 后台并发同步账户数 |
| `DAILY_SNAPSHOT_TIME` | `23:55` | 每日快照时间（`HH:MM`） |
| `CORS_ALLOW_ORIGINS` | 本地前端地址 | 允许的跨域来源，逗号分隔 |
| `ENABLE_POSITION_ORDER_EDIT` | `true` | 是否允许编辑本地仓位订单 |
| `SPOT_DUST_THRESHOLD_USD` | `0.01` | 忽略现货零碎余额的美元阈值 |

前端的 `VITE_API_BASE_URL` 为可选项。未设置时，Vite 开发服务器会把 `/api` 和 `/health` 代理到 `http://127.0.0.1:8000`。详见 [frontend/README.md](frontend/README.md)。

## API 概览

以下只列出主要资源；请求参数和完整模型以 OpenAPI 为准。

| 资源 | 主要路径 | 用途 |
| --- | --- | --- |
| 健康与总览 | `/health`、`/api/v1/overview` | 服务状态、权益和同步汇总 |
| 交易所与账户 | `/api/v1/exchanges`、`/api/v1/accounts` | 交易所、账户及手动同步 |
| 连接检测 | `/api/v1/exchange-connections` | 查看并测试只读 API 连接 |
| 仓位与行情 | `/api/v1/positions`、`/api/v1/positions/prices` | 分仓/合仓、现货/合约与公开行情 |
| 本地订单 | `/api/v1/position-orders`、`/api/v1/positions/{id}/close-*` | 订单批次与本地平仓核算 |
| 历史回填 | `/api/v1/accounts/{id}/history-import/*` | Bitget 历史预览与提交 |
| 盈亏与绩效 | `/api/v1/pnl`、`/api/v1/performance/*` | 权益、回撤和交易统计 |
| 快照与手动录入 | `/api/v1/snapshots/*`、`/api/v1/manual/snapshot` | 日快照查询、生成与补录 |
| Symbol 映射 | `/api/v1/symbols` | 交易所 Symbol 标准化配置 |

## 项目结构

```text
posihub/
├─ backend/
│  ├─ app/
│  │  ├─ api/                 # FastAPI 路由
│  │  ├─ core/                # 配置、加密、日志、调度器
│  │  ├─ db/                  # SQLModel 模型与会话
│  │  ├─ schemas/             # API DTO
│  │  └─ services/            # 同步、行情、回填、盈亏与绩效服务
│  ├─ tests/
│  └─ requirements.txt
├─ frontend/
│  ├─ src/api/                # Axios、React Query hooks 与类型
│  ├─ src/components/
│  ├─ src/i18n/
│  ├─ src/pages/
│  └─ src/theme/
├─ scripts/                   # 初始化、Symbol 种子与数据修复脚本
├─ docs/                      # 产品/开发说明
└─ .env.example
```

## 验证

```powershell
Set-Location backend
python -m pytest

Set-Location ..\frontend
npm.cmd run test
npm.cmd run build
```

## 安全与部署边界

- 只为交易所 API Key 授予读取余额、仓位和历史记录所需的最小权限；不要授予交易或提现权限。
- API Key、Secret 和 Passphrase 使用 Fernet 加密后写入数据库，接口只返回脱敏后的 API Key。
- 实时价格来自公开 ticker 请求，只覆盖页面展示，不会写入仓位、余额或快照。
- 当前应用没有内置用户认证，默认只监听 `127.0.0.1`。如需远程访问，请使用 HTTPS、反向代理和访问控制，不要直接暴露 API。
- 数据默认保存在 `backend/posihub.db`。执行数据修复或迁移前请备份数据库。

## 延伸文档

- [前端说明](frontend/README.md)
- [交易账户与仓位管理开发说明](docs/trading-account-position-management-dev.md)
