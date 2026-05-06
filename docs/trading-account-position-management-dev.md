# 交易账户与仓位管理系统开发文档（个人版）

## 1. 项目目标

构建一个**仅个人使用**的交易账户与仓位管理系统，统一监控多个交易所的资产、仓位和盈亏；优先稳定和可维护，不追求复杂架构。

核心原则：

- 以 `read-only API` 为主，保障资金安全。
- 可手动录入，保证数据连续性。
- 每日快照沉淀历史数据，支持长期复盘。
- 统一 Symbol 映射，消除交易所命名差异。

---

## 2. 范围与功能清单

## 已给需求（转为可实现项）

1. **多交易所聚合**
  - 支持接入多个交易所账户（同交易所多子账户也支持）。
  - 统一展示总资产、总仓位、总未实现盈亏、已实现盈亏（可选）。
2. **Read-only API 接入**
  - 仅保存只读 Key（禁止提现/交易权限）。
  - 每个账户可独立启停同步任务。
3. **仓位 / 盈亏 / 账户页面**
  - 账户页：余额、可用、冻结、资金曲线（按日）。
  - 仓位页：方向、开仓均价、标记价、未实现盈亏、杠杆、保证金模式。
  - 盈亏页：按交易所、按标的、按时间维度查看。
4. **手动录入**
  - 提供“手动快照录入”表单。
  - 支持补录某一天关键数据（净值、仓位、成本价等）。
  - 标记数据来源：`api` / `manual`。
5. **分仓 / 合仓视图**
  - 分仓：按交易所 / 子账户 / 账户类型展示。
  - 合仓：按统一 Symbol、方向聚合展示净暴露与综合成本。
6. **历史快照（每日一次）**
  - 每日固定时间（如 23:55 本地时间）写入账户与仓位快照。
  - 保留全量历史，支持净值曲线与回溯。
7. **统一 Symbol 映射**
  - 现货 `BTC/USDT`、U 本位 `BTCUSDT`、币本位 `BTCUSD` 映射到统一主键。
  - 统一字段：基础币、计价币、合约类型、乘数、到期日（如有）。

---

## 3. 补充缺失需求（建议纳入 MVP）

## 3.1 功能性补充

- **账户类型区分**：现货、U 本位永续、币本位永续、交割合约、理财/资金账户。
- **数据刷新策略**：手动刷新 + 定时刷新（如每 1~5 分钟）。
- **错误可观测性**：最近一次同步状态、失败原因、连续失败次数。
- **数据修正机制**：手动覆盖后保留原始记录（审计字段）。
- **导出能力**：CSV 导出（仓位、日快照、净值曲线）。

## 3.2 非功能补充

- **安全**
  - API Key 本地加密存储（至少使用环境变量 + 本地加密文件）。
  - 严禁在日志中打印完整密钥。
  - 默认仅本机访问（`127.0.0.1`）。
- **可靠性**
  - 交易所 API 超时、限频、临时失败时自动重试（指数退避）。
  - 单交易所故障不影响其他交易所数据展示。
- **性能**
  - 单用户、低并发目标：页面打开 < 2 秒（本地环境）。
  - 快照查询支持分页与按日期过滤。
- **可维护性**
  - 核心模块解耦：接入层、标准化层、存储层、展示层。
  - 关键逻辑（symbol 映射、聚合）配套单元测试。

---

## 4. 技术栈（简单且够用）

## 4.1 后端

- **Python 3.12**
- **FastAPI**：提供 REST API。
- **SQLModel / SQLAlchemy**：ORM 与数据模型。
- **SQLite**（MVP）：单机个人场景足够；后续可平滑升级 PostgreSQL。
- **APScheduler**：定时任务（分钟刷新 + 每日快照）。
- **CCXT**：统一交易所只读接口（余额、仓位、行情）。
- **Pydantic**：数据校验与序列化。

## 4.2 前端

- **React + Vite + TypeScript**
- **Ant Design**（或 Mantine）快速搭建后台页面
- **ECharts**：净值、盈亏、仓位占比图
- **TanStack Query**：请求缓存与刷新管理

## 4.3 运维与工程

- **Pytest**：后端测试
- **Vitest**：前端测试（可选）
- **Ruff + Black**：Python 代码规范

> 为了最简落地：可先本地直跑（不容器化），稳定后再加 Docker。

---

## 5. 系统架构（MVP）

数据流：

1. Scheduler 触发同步任务。
2. Exchange Connector（CCXT）拉取原始账户/仓位数据。
3. Normalizer 标准化字段 + SymbolMapper 统一映射。
4. Aggregator 计算分仓与合仓指标。
5. 写入 DB（当前状态表 + 每日快照表）。
6. API 提供给前端页面展示。
7. 用户允许通过 Manual Entry 写入补录数据。
8. 允许模拟账户(不设置api，能够调整账户余额，手动输入仓位数据)

---

## 6. 数据模型设计（核心表）

## 6.1 基础配置

- `exchanges`
  - `id`, `name`, `enabled`, `created_at`
- `accounts`
  - `id`, `exchange_id`, `account_name`, `api_key_enc`, `api_secret_enc`, `passphrase_enc`, `enabled`, `created_at`

## 6.2 标准化字典

- `symbol_mappings`
  - `id`
  - `exchange`
  - `raw_symbol`（如 `BTC/USDT`, `BTCUSDT`, `BTCUSD_PERP`）
  - `canonical_symbol`（如 `BTC-USDT-PERP`, `BTC-USD-PERP`, `BTC-USDT-SPOT`）
  - `base_asset`, `quote_asset`
  - `instrument_type`（`spot` / `perp` / `futures`）
  - `contract_size`
  - `is_active`

## 6.3 运行态数据

- `account_balances_current`
  - `account_id`, `asset`, `equity`, `available`, `frozen`, `updated_at`, `source`
- `positions_current`
  - `account_id`, `canonical_symbol`, `side`, `qty`, `entry_price`, `mark_price`, `unrealized_pnl`, `leverage`, `margin_mode`, `updated_at`, `source`

## 6.4 历史快照

- `account_snapshots_daily`
  - `snapshot_date`, `account_id`, `total_equity`, `total_unrealized_pnl`, `source`, `created_at`
- `position_snapshots_daily`
  - `snapshot_date`, `account_id`, `canonical_symbol`, `side`, `qty`, `entry_price`, `mark_price`, `unrealized_pnl`, `source`, `created_at`

## 6.5 手动录入审计

- `manual_entries`
  - `id`, `entry_date`, `account_id`, `entry_type`, `payload_json`, `operator`, `created_at`

---

## 7. Symbol 统一映射方案

统一键建议：

`{BASE}-{QUOTE}-{INSTRUMENT_TYPE}`  
示例：

- 现货：`BTC-USDT-SPOT`
- U 本位永续：`BTC-USDT-PERP`
- 币本位永续：`BTC-USD-PERP`

映射规则：

1. 优先使用交易所返回的合约元数据（市场类型、结算币、合约乘数）。
2. 对歧义符号建立人工映射白名单（配置表）。
3. 聚合展示时默认按 `canonical_symbol` 合并；可切换“按账户分开”。

---

## 8. API 设计（示例）

- `GET /api/v1/overview`
  - 返回总资产、总仓位数、总未实现盈亏、最近快照时间
- `GET /api/v1/accounts`
  - 返回账户列表 + 同步状态
- `POST /api/v1/accounts/{id}/sync`
  - 手动触发单账户同步
- `GET /api/v1/positions?view=split|merged`
  - 分仓/合仓视图
- `GET /api/v1/pnl?range=7d|30d|90d`
  - 盈亏曲线数据
- `POST /api/v1/manual/snapshot`
  - 手动录入当日账户/仓位快照
- `GET /api/v1/snapshots/daily`
  - 按日期查看历史快照

---

## 9. 目录结构（建议）

```text
posihub/
  docs/
    trading-account-position-management-dev.md
  backend/
    app/
      main.py
      api/
        routes_overview.py
        routes_accounts.py
        routes_positions.py
        routes_pnl.py
        routes_manual.py
      core/
        config.py
        security.py
        scheduler.py
      db/
        session.py
        models.py
        repositories/
      services/
        exchange/
          base.py
          ccxt_client.py
          adapters/
        normalize/
          symbol_mapper.py
          normalizer.py
        aggregate/
          position_aggregator.py
          pnl_calculator.py
      tests/
        test_symbol_mapper.py
        test_position_aggregator.py
    requirements.txt
  frontend/
    src/
      main.tsx
      api/
      pages/
        OverviewPage.tsx
        AccountsPage.tsx
        PositionsPage.tsx
        PnlPage.tsx
        ManualEntryPage.tsx
      components/
      hooks/
      types/
    package.json
  scripts/
    init_db.py
    seed_symbol_mapping.py
  .env.example
  docker-compose.yml
  README.md
```

---

## 10. 里程碑（建议 3 个阶段）

## Phase 1 - MVP（1~2 周）

- 单交易所接入 + 只读 API 校验
- 账户页、仓位页、总览页
- 每日快照入库
- 手动录入页面与接口
- 分仓/合仓完整视图

## Phase 2 - 多交易所与映射增强（1 周）

- 多交易所并发同步
- Symbol 映射白名单 + 冲突处理

## Phase 3 - 稳定性与体验（1 周）

- 重试、限流、失败告警（本地通知/邮件可选）
- CSV 导出
- 测试补齐与部署脚本完善

---

## 11. 验收标准（MVP）

- 至少接入 2 个交易所账户并成功展示聚合数据。
- 关闭某交易所 API 后，系统仍可展示其他账户数据。
- 手动录入可覆盖 API 缺失日期，并在图表中连续展示。
- 每天自动生成快照，且可按日期回查。
- 同一标的在不同交易所命名可正确统一映射并聚合。

---

## 12. 后续可选增强（非 MVP）

- 移动端适配（PWA）
- 多币种折算（统一 USD 或 USDT 计价）
- 风险指标（保证金率、爆仓价格预警）
- 接入消息通知（Telegram/企业微信）
- 成交明细与归因分析（需要更细粒度交易数据）

