# Bitget 统一账户（UTA）升级实施计划

> 状态：规划完成，待实施
> 编制日期：2026-09-07
> 评估基线：`feat/connection-check-and-live-price` / `161f340`
> 范围：PosiHub 的 Bitget 只读同步、历史回填、汇总展示与本地数据迁移

本文是升级与切换计划，不表示已经修改 Bitget 账户模式，也不表示业务代码已经完成适配。实际切换必须在本文的测试门槛全部通过后，由操作人在维护窗口内执行。

## 1. 结论与已确定方案

本次升级采用以下方案：

1. 新增专用账户类型 `bitget_uta`，不把 Bitget UTA 的语义推广到其他交易所。
2. 一个 Bitget UID 在 PosiHub 中只保留一个启用的 `bitget_uta` 账户；现货、U 本位和币本位不再各建一个启用账户。
3. 因现有系统需要继续读取 `COIN-FUTURES`，Bitget 侧必须使用 **Advanced Mode**。Basic Mode 不满足币本位范围。
4. CCXT 从 `4.5.52` 固定升级到 `4.5.77`，并由 PosiHub 显式设置 `uta=True`。不把 CCXT 的自动探测作为路由依据。
5. 继续使用只读 API Key。账户设置、资产、当前仓位、历史订单和成交均走只读路径；需要读写权限的历史仓位接口只作为可选校验，权限不足时给出警告，不阻断订单/成交回填。
6. 首期支持现货资产、`USDT-FUTURES` 和 `COIN-FUTURES`。`USDC-FUTURES` 与现货杠杆不在首期范围；预检发现相关敞口或债务时必须阻断切换，不能静默忽略。
7. UTA 总权益只采信 `/api/v3/account/assets` 的顶层 `usdtEquity`，每次只计入一次。不能把各经典账户余额继续相加，也不能只取 USDT/USDC/USD 余额代替统一账户权益。
8. 现有经典账户逻辑保持兼容；通过 `account_type` 分流，不设置全局 UTA 开关。

## 2. 当前基线与影响证据

### 2.1 代码现状

| 范围 | 当前行为 | UTA 风险 |
| --- | --- | --- |
| 账户建模 | `spot`、`usdt_perp`、`coin_perp` 分开建账 | 同一共享资产池被多个账户重复读取和汇总 |
| CCXT | 固定 `ccxt==4.5.52`，未显式启用 UTA | 可能继续路由到经典 v2；行为依赖 CCXT 版本默认值 |
| 币本位同步 | 直接调用经典 `/api/v2/mix/account/accounts` 发现保证金币种 | 账户升级后经典私有接口不再是正确数据源 |
| 现货持仓 | 用余额 `equity` 直接生成现货数量 | UTA 的 `equity` 会包含冻结保证金及未实现盈亏，不能当钱包币数 |
| 仓位 PnL | 根据账户类型判断是否把币本位 PnL 换算为 USDT | 一个 UTA 账户内同时存在 linear 与 inverse 仓位，账户级判断失效 |
| 总览 | 汇总 USDT、USDC、USD 三种余额 | 漏掉非稳定币抵押资产的价值，也可能重复计算共享池 |
| 快照/绩效 | 按账户和结算资产保存、筛选 | 三个来源账户合并后需要一个唯一的 UTA 总权益口径 |
| 历史回填 | 仅支持 `usdt_perp`、`coin_perp`；时间窗为 90 天 | UTA 每次查询跨度最多 30 天，且一个账户必须显式选择产品范围 |
| 数据库升级 | 只有 `SQLModel.metadata.create_all()` | `create_all()` 不会给已有 SQLite 表补列，必须有显式迁移步骤 |

### 2.2 本地数据盘点

2026-09-07 的只读盘点结果如下；表中不包含任何密钥或资产金额：

| ID | 当前名称 | 类型 | 当前余额行 | 当前仓位行 | 迁移角色 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | `bitgetU本位` | `usdt_perp` | 1 | 12 | 待停用来源 |
| 2 | `bitget币本位` | `coin_perp` | 1 | 2 | 待停用来源 |
| 3 | `bitget现货` | `spot` | 2 | 1 | 建议目标账户候选 |

ID 3 仅是候选，因为它已经持有现货 `PositionCurrent`，迁移时需要移动的父记录更少。迁移脚本不得硬编码该选择，必须显式传入目标 ID 和来源 ID。

三个记录当前使用的 API Key 并不相同。不同 Key 既不能证明它们属于不同 UID，也不能证明属于同一 UID；合并前必须通过已鉴权的账户信息接口比较 `userId`/`uid`。当前两个历史回填预览均已过期，但切换前仍需重新检查是否出现新的未过期、未提交预览。

## 3. 范围与非目标

### 3.1 首期必须覆盖

- Bitget UTA 身份、模式、权限和能力预检；
- 统一资产及顶层 USDT 折算权益；
- 现货资产持仓；
- U 本位和币本位当前仓位；
- 订单、成交和可选的历史仓位校验；
- 总览、快照、绩效、实时价格和账户页的 UTA 兼容；
- 三个现有逻辑账户向一个 UTA 账户的可回滚迁移；
- 经典 Bitget 账户以及其他交易所的回归兼容。

### 3.2 首期明确不做

- 下单、撤单、划转、提现、调整杠杆、调整保证金或切换账户模式；
- WebSocket 私有频道；
- 现货杠杆、借贷和负债建模；
- `USDC-FUTURES` 仓位与历史回填；
- 历史净值按历史价格重新估值；
- 通用的“账户组”或跨交易所统一账户框架。

PosiHub 只负责读取和迁移本地数据。Bitget 账户模式切换由操作人在 Bitget 官方界面完成，应用不得调用任何切换或交易写接口。

## 4. 目标模型与数据流

```mermaid
flowchart LR
    A[一个 Bitget UID\n一个启用的 bitget_uta 账户]
    A --> B[/api/v3/account/assets]
    A --> C[USDT-FUTURES 当前仓位]
    A --> D[COIN-FUTURES 当前仓位]
    A --> E[按产品范围读取订单与成交]
    B --> F[原生币种余额]
    B --> G[唯一 usdtEquity]
    B --> H[现货资产持仓\n使用 balance 数量]
    C --> I[标准化衍生品仓位]
    D --> I
    F --> J[account_balances_current]
    G --> K[总览与每日 USDT 汇总快照]
    H --> L[positions_current]
    I --> L
    E --> M[订单级持仓与已实现 PnL]
```

### 4.1 关键不变量

实现和迁移完成后必须始终满足：

- 同一 Bitget UID 最多只有一个启用的 `bitget_uta` 账户；
- 一次同步只请求和保存一次共享资产池；
- UTA 总权益等于顶层 `usdtEquity`，不再从多个账户或多个币种重复相加；
- 现货数量来自资产项的 `balance`，不是 `equity`；
- 每条衍生品仓位在标准化之前携带产品类别，币本位换算不能依赖账户类型；
- 任一必需类别请求失败时，本次同步整体失败并保留上一次完整数据；
- 来源账户停用但不删除，历史审计数据不丢失；
- 应用代码中不存在交易、账户切换或资金写接口。

### 4.2 UTA 账户类型

在 `AccountType` 增加：

```text
BITGET_UTA = "bitget_uta"
```

约束如下：

- 只有 `exchange.name == "bitget"` 可以选择该类型；
- 新建 UTA 账户默认应先停用，连接测试成功且 UID 不冲突后才允许启用；
- Bitget 连接测试为经典和 UTA 记录都保存 UID；同 UID 已有启用的 UTA 记录时，不允许再启用任何经典记录，反向亦然；
- 不同子账户 UID 可以分别建立 UTA 记录，不能按主账户名称或 `parentId` 合并；
- 经典 `spot`、`usdt_perp`、`coin_perp` 的行为不变；
- 账户页显示“Bitget 统一账户”，并明确列出首期读取范围。

### 4.3 交换层中立数据

在现有轻量数据类上增加字段，不创建新的适配器层级：

| 类型 | 新字段 | 用途 |
| --- | --- | --- |
| `RawBalance` | `wallet_balance: float | None` | UTA 资产项的 `balance`；生成现货数量 |
| `RawBalance` | `usd_value: float | None` | 对账和诊断；首期不落库 |
| `RawBalance` | `debt: float` | 预检现货杠杆负债；非零时阻断 |
| `RawPosition` | `product_type: str | None` | `USDT-FUTURES`/`COIN-FUTURES`；决定 PnL 单位和诊断范围 |
| `FetchResult` | `total_equity_usdt: float | None` | UTA 顶层 `usdtEquity`；经典账户保持 `None` |

`CcxtExchangeClient` 对 UTA 账户从同一次资产响应解析余额明细和 `usdtEquity`。如果 CCXT 标准化结果丢失顶层字段，只在现有 Bitget 客户端内部使用对应的 v3 只读原始方法；不要把 Bitget 原始结构泄漏到同步服务。

### 4.4 最小数据库变化

只增加两个可空列：

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `accounts` | `current_equity_usdt REAL NULL` | 最近一次完整 UTA 同步的顶层 `usdtEquity`；经典账户为空 |
| `exchange_connection_states` | `details_json TEXT NULL` | 保存 UID、账户模式、等级、持仓模式、权限和能力的脱敏诊断 |

不向 `positions_current` 增加产品类别列。当前仓位在同步边界完成单位换算后统一以 USDT 表示；现货/永续由 canonical symbol 后缀区分，U 本位与币本位由 canonical quote 和现有符号映射区分。若契约测试证明存在 canonical 冲突，再单独评审字段扩展，首期不预先增加。

`details_json` 可以保存完整 UID 供后端防重，经典 Bitget 连接测试使用 v2 `userId`，UTA 使用 v3 `userId/uid`。API 和日志只返回脱敏值。该字段不能包含 API Key、Secret、Passphrase、请求签名、余额或仓位数量。

### 4.5 权益和快照口径

- `account_balances_current` 继续保存每种币的原生 `equity`、`available`、`frozen/locked`；
- `accounts.current_equity_usdt` 保存 UTA 唯一总权益；
- 总览对 `bitget_uta` 只读取一次 `current_equity_usdt`，并排除该账户的逐币余额汇总；
- 每日快照对 UTA 只写一条 `asset="USDT"` 的账户汇总行，`total_equity=current_equity_usdt`；逐仓位快照照常写入；
- UTA 的 `total_available` 没有等价的顶层字段，首期写 `0`，不能把不同币种的 `available` 直接相加；
- 总览只统计启用账户，避免已退役来源账户继续进入当前总数和当前权益。

历史快照不重写、不重新估值，仍保留在原来源账户下。绩效服务通过 `bitget-uta-cutover-v1` 的时间戳，使统一账户只读取切换日起的新口径快照；界面显示“UTA 口径起始日”。切换前记录仍可在快照页或导出中按原账户查看。这样避免目标账户既有的现货快照与 UTA 总权益混成一条看似连续、实则口径不同的曲线，也避免把旧的原生币余额伪装成历史 USDT 市值。

## 5. Bitget 与 CCXT 接口策略

### 5.1 只读接口矩阵

| 目的 | 接口 | 必需权限 | 失败处理 |
| --- | --- | --- | --- |
| 切换前 UID 核对 | `GET /api/v2/spot/account/info` | 经典账户只读 | 任一凭据 UID 不同则禁止合并 |
| UTA UID/权限 | `GET /api/v3/account/info` | 无额外业务权限 | `permType` 非只读或缺少范围则禁止切换 |
| 模式/等级 | `GET /api/v3/account/settings` | UTA management read | 过渡状态或非 Advanced 则禁止切换 |
| 资产/总权益 | `GET /api/v3/account/assets` | UTA management read | 同步整体失败，不写部分数据 |
| 当前仓位 | `GET /api/v3/position/current-position` | UTA trade read | 任一首期类别失败则同步整体失败 |
| 历史订单 | `GET /api/v3/trade/history-orders` | UTA trade read | 预览不可提交 |
| 历史成交 | `GET /api/v3/trade/fills` | UTA trade read | 预览不可提交 |
| 历史仓位 | UTA position history | 官方当前标注 trade read/write | 权限不足只关闭 PnL 交叉校验并显示警告 |

UTA 连接测试应顺序执行账户信息、账户设置、资产、`USDT-FUTURES` 当前仓位和 `COIN-FUTURES` 当前仓位。另行探测 `USDC-FUTURES` 与资产 `debt`：只要存在非零首期外敞口，就返回阻断项。经典 Bitget 连接测试额外读取 v2 账户信息，以便在实际切换前完成 UID 防重和三组凭据的一致性核对。

允许的稳定状态是 `accountMode in {unified, hybrid}` 且 `accountLevel == advanced`；`upgrading` 和 `switching` 必须视为暂态失败，等待平台完成后重试。`one_way_mode` 与 `hedge_mode` 均可支持，现有 `(account_id, canonical_symbol, side)` 唯一键可以区分双向持仓。

### 5.2 CCXT 路由

- `backend/requirements.txt` 精确固定 `ccxt==4.5.77`；
- `build_client_for_account()` 对 `bitget_uta` 传入显式 `uta=True`；
- UTA 资产请求不传经典 `productType`；
- UTA 仓位和历史请求使用 v3 `category`；
- 经典币本位的 v2 保证金币种发现逻辑只保留在 `coin_perp` 分支，UTA 分支不可调用；
- 优先使用 CCXT 的统一方法；只有契约测试证明其丢字段、强制 symbol 或分页不完整时，才在现有 Bitget 客户端中加入一个窄范围 v3 原始调用；
- 每次依赖升级都用脱敏 fixture 固定关键响应字段，避免上游解析变化静默改变净值。

### 5.3 同步原子性

UTA 同步顺序：

1. 获取账户资产及 `usdtEquity`；
2. 获取 `USDT-FUTURES` 当前仓位；
3. 获取 `COIN-FUTURES` 当前仓位；
4. 由 `wallet_balance` 生成现货资产持仓；
5. 按每条 `product_type` 标准化衍生品 PnL；
6. 合并现货和衍生品仓位；
7. 所有请求和标准化均成功后，才在一个数据库事务中 upsert 余额、仓位和账户权益；
8. 最后刷新订单级仓位并更新同步状态。

任一步失败都不得把空列表当成成功结果。真正的空仓响应可以清除对应旧仓位；网络、鉴权、限流或解析异常必须保留上次完整状态并标记同步失败。

## 6. 历史回填设计

### 6.1 请求契约

`HistoryImportPreviewRequest` 增加可空字段：

```text
product_scope: "usdt_perp" | "coin_perp" | null
```

- `bitget_uta` 必须显式选择一个范围；
- 经典 `usdt_perp`、`coin_perp` 继续由账户类型推导，并拒绝冲突参数；
- `product_scope` 必须写入 `HistoryImportPreview.payload_json`；提交阶段只使用缓存范围，不重新推断；
- 前端统一账户的历史回填弹窗增加“U 本位 / 币本位”单选项。

### 6.2 时间窗与分页

- 单个 UTA 请求窗口最多 30 天；
- 可查询历史只覆盖最近 90 天；请求早于可用范围时直接返回可读的 blocker，不静默截断；
- 长于 30 天的用户区间拆成连续窗口，边界采用左闭右开，最终终点包含一次，避免重复或遗漏；
- 每个窗口使用 cursor 分页，并按 `orderId`、`tradeId/execId` 跨页和跨窗口去重；
- 当前 90 天 `_HISTORY_WINDOW_MS` 改为 Bitget UTA 的 30 天窗口常量，经典路径也可安全使用较小窗口；
- 任一订单或成交窗口失败，整个预览标记 incomplete 且禁止提交，不能像当前实现一样记录 warning 后继续提交部分结果。

历史仓位仍只是对账来源。若只读 Key 无法访问该接口：

- `closed_positions=[]`；
- 返回 `validation_unavailable` 警告；
- 订单和成交都完整时仍可提交；
- 不要求用户把 Key 改成读写权限。

### 6.3 UTA 字段兼容

为以下 v3 字段增加 fixture 和解析覆盖：`category`、`posSide`、`createdTime`、`updatedTime`、`openPriceAvg`、`closePriceAvg`、`cumRealisedPnl`、`netProfit`、`execPnl`。规范化后继续复用现有 FIFO、去重和 blocker 逻辑，不重写订单账本。

## 7. 代码变更清单

以下是预计变更范围；实施时应优先在现有文件中完成，不新增通用框架。

| 文件 | 最小改动 |
| --- | --- |
| `backend/requirements.txt` | 固定 CCXT `4.5.77` |
| `backend/app/db/models.py` | 增加 `BITGET_UTA`、`current_equity_usdt`、`details_json` |
| `backend/app/services/exchange/base.py` | 扩展 `RawBalance`、`RawPosition`、`FetchResult` |
| `backend/app/services/exchange/factory.py` | 仅 Bitget UTA 显式启用 `uta=True` |
| `backend/app/services/exchange/ccxt_client.py` | v3 资产、分类仓位、顶层权益、30 天历史窗口及失败语义 |
| `backend/app/services/sync_service.py` | 增加 UTA 聚合分支并保持全有或全无写入 |
| `backend/app/services/spot/position_deriver.py` | 数量优先使用 `wallet_balance`，经典账户回退 `equity` |
| `backend/app/services/normalize/normalizer.py` | 按 `RawPosition.product_type` 处理币本位 PnL |
| `backend/app/services/position_market.py` | UTA 按 canonical instrument 判断现货/衍生品 |
| `backend/app/services/live_prices.py` | UTA fallback symbol 按 canonical 类型和 quote 路由 |
| `backend/app/api/routes_accounts.py` | 扩展连接测试、脱敏详情和重复 UID 校验 |
| `backend/app/schemas/account.py`、`exchange.py` | 暴露 UTA 类型、只读能力与口径起始提示 |
| `backend/app/api/routes_overview.py` | UTA 权益只计一次，并排除停用账户 |
| `backend/app/services/snapshot_service.py` | UTA 每日只写一条账户 USDT 汇总快照 |
| `backend/app/services/performance/equity_metrics.py` | 正确读取 UTA 汇总快照，并按 cutover 标记限定口径起始日 |
| `backend/app/schemas/history_import.py` | 增加 `product_scope` 和完整性/校验警告 |
| `backend/app/services/history_import/scope.py` | 账户类型与显式产品范围解析 |
| `backend/app/services/history_import/bitget_fetcher.py` | v3 分类、完整性失败和可选仓位校验 |
| `backend/app/services/history_import/normalize_bitget.py` | 补齐 UTA v3 字段映射 |
| `frontend/src/api/types.ts` | 增加 `bitget_uta`、连接详情和历史范围类型 |
| `frontend/src/pages/AccountsPage.tsx` | 增加 UTA 标签、范围说明和历史回填入口 |
| `frontend/src/components/HistoryImportModal.tsx` | UTA 产品范围选择与 warning/blocker 展示 |
| `scripts/migrate_bitget_uta.py` | 新增唯一必要的 schema/数据迁移与预检脚本 |

## 8. 数据库与现有数据迁移

### 8.1 迁移脚本接口

新增 `scripts/migrate_bitget_uta.py`，默认只做 dry-run。建议子命令：

```text
python scripts/migrate_bitget_uta.py schema --apply
python scripts/migrate_bitget_uta.py probe --target-account-id 3 --source-account-ids 1 2
python scripts/migrate_bitget_uta.py cutover --target-account-id 3 --source-account-ids 1 2 --apply
```

脚本应复用当前 `repair_coin_pnl_units.py` 的安全模式：SQLite 备份、结构化 JSON 报告、`DataMigration` 幂等标记和默认 dry-run。建议标记为 `bitget-uta-schema-v1`、`bitget-uta-cutover-v1`。

### 8.2 schema 阶段

由于 `create_all()` 不会修改既有表，`schema --apply` 必须在启动新后端前执行：

1. 确认数据库为预期 SQLite 文件；
2. 使用 SQLite backup API 创建一致性备份；
3. 计算并输出 SHA-256；
4. 通过 `PRAGMA table_info` 判断列是否存在；
5. 仅对缺失列执行 `ALTER TABLE ... ADD COLUMN`；
6. 写入 schema 幂等标记；
7. 再次读取表结构并退出。

重复执行必须是无副作用的成功；任何列类型不符都应停止，而不是尝试自动重建表。

### 8.3 probe 阶段

`probe` 只发只读请求，不改数据库。必须验证：

- 目标和所有来源记录都属于 Bitget；
- v2 账户信息返回相同 `userId`；切换后 v3 信息和设置返回相同 `userId/uid`；
- Key 的 `permType` 是只读，拥有 UTA management/trade 读取能力，不含提现权限；
- `accountLevel=advanced`，账户不处于 `upgrading`/`switching`；
- U 本位与币本位当前仓位均能读取；
- 无非零 USDC 仓位、现货杠杆债务或其他首期不支持敞口；
- 顶层 `usdtEquity` 有限且非负；资产 `usdValue` 合计与 `accountEquity` 在容差内；
- 不输出密钥、签名、原始请求头、完整 UID 或资产金额。

UID 不一致时立即停止。不能因为账户名称相似、API Key 相同/不同或余额相近而绕过检查。

### 8.4 cutover 事务

实际写入前再次执行全部离线和在线检查，然后在一个数据库事务中：

1. 确认没有未过期且未提交的历史预览；删除过期预览；
2. 检查目标与来源的 `(canonical_symbol, side)` 是否冲突；有冲突时停止，首期不自动合并；
3. 把来源账户的 `PositionCurrent.account_id` 改为目标 ID，保留 `PositionCurrent.id`，使订单和关闭记录的外键继续有效；
4. 清空目标及来源账户的 current balance 行，等待第一次 UTA 同步写入唯一共享池；
5. 将目标类型改为 `bitget_uta`，写入已验证的凭据诊断；
6. 启用目标，停用所有来源账户；
7. 清空来源账户的同步状态，避免旧成功状态造成误解；
8. 写入包含账户 ID、行数和脱敏 UID 指纹的 `DataMigration` 记录；
9. 提交事务后立即执行一次 UTA 同步和一次临时快照校验。

`PositionOrder`、`PositionCloseExecution` 和 `PositionOrderMatch` 不改主键或外键；它们通过未变化的父 `PositionCurrent.id` 自动归入目标账户。历史 `AccountSnapshotDaily`、`PositionSnapshotDaily` 和 `ManualEntry` 留在原账户中，作为切换前审计记录，不做语义不可靠的重估值或归并。

如果来源与目标仓位键冲突，操作人应先调查符号映射或重复记录。迁移脚本不得猜测哪一条父仓位应保留。

## 9. 分阶段实施与门槛

| 阶段 | 内容 | 进入下一阶段的门槛 |
| --- | --- | --- |
| G0 基线冻结 | 保存脱敏 fixture、数据库备份、当前账户/仓位/订单计数 | 备份可读取；基线测试全绿 |
| G1 模型与依赖 | CCXT、账户类型、两列 schema、客户端显式 UTA 开关 | 经典账户测试无回归；schema 重跑幂等 |
| G2 当前同步 | v3 资产、分类仓位、现货派生、PnL、总览和快照 | fixture 测试全绿；部分失败不写库 |
| G3 历史与前端 | 产品范围、30 天分页、只读降级、页面文案 | 90 天边界、去重、blocker 和 UI 流程通过 |
| G4 迁移演练 | 在生产数据库副本执行 probe/dry-run/apply | 行数、FK、唯一键和幂等结果全部一致 |
| G5 实际切换 | Bitget 切 Advanced，执行 probe、cutover、首次同步 | 与 Bitget 页面对账通过；连续 3 次同步成功 |
| G6 观察 | 保留来源账户和备份，观察至少 24 小时 | 无重复权益、漏仓、历史缺口或持续错误 |

建议按三个可审查的实现提交组织：

1. UTA 模型、CCXT 路由与当前同步；
2. 汇总、快照、历史回填与前端；
3. 幂等迁移脚本及切换运行手册。

不要在同一提交中混入无关重构。

## 10. 测试计划

### 10.1 单元与契约测试

- UTA 工厂只对 Bitget 设置 `uta=True`，经典分支保持原参数；
- 资产 fixture 正确解析 `usdtEquity`、`equity`、`balance`、`available`、`locked`、`debt` 和 `usdValue`；
- `balance != equity` 时，现货 qty 必须等于 `balance`；
- U 本位 PnL 保持 USDT，币本位 PnL 只转换一次；
- hedge mode 下同 symbol 的 long/short 均保留；
- USDT/COIN 任一请求异常时，旧 current 数据和权益不变；
- 空仓成功响应能清理无子记录仓位，并保持有订单子记录的父 ID；
- 总览对一个 UTA UID 只计一次 `current_equity_usdt`；
- UTA 每天只产生一个账户级 USDT 快照；
- 目标账户切换前的现货快照不进入 UTA 绩效曲线；
- 经典 Bitget、其他交易所、模拟账户的既有测试继续通过。

### 10.2 历史测试

- 30 天整边界、跨两个/三个窗口和最近 90 天边界；
- cursor 多页与窗口边界重复数据去重；
- UTA 账户未传 `product_scope` 时返回 400；
- U 本位和币本位数据互不串入；
- 订单或成交任一窗口失败时 preview 不可提交；
- 历史仓位权限不足时仅显示 `validation_unavailable`；
- UTA v3 的时间、方向、成交 PnL 和累计已实现 PnL 字段正确解析；
- preview 提交继续保持确定性，不在 commit 时重新访问交易所。

### 10.3 迁移测试

- dry-run 零写入；
- 不同 UID、非 Bitget、非 Advanced、读写 Key、USDC 敞口、非零 debt、活动 preview、仓位键冲突分别阻断；
- apply 后只有目标账户启用；
- 父仓位 ID 不变，所有订单/关闭/匹配外键可达；
- 来源 current balance 为空，目标首次同步后只有一份资产池；
- 历史快照和手工审计仍留在来源账户；
- 二次执行返回 already applied，不重复移动数据；
- 从备份恢复后，基线行数和哈希校验一致。

### 10.4 验证命令

实施时至少运行：

```text
python -m pytest backend/tests
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
python scripts/migrate_bitget_uta.py probe --target-account-id <id> --source-account-ids <ids>
```

若前端实际脚本名称与上面不同，以 `frontend/package.json` 的现有脚本为准，不为迁移额外引入测试框架。

## 11. 实际切换运行手册

### 11.1 维护窗口前

- 完成 G0-G4；
- 确认 Bitget 官方当前仍允许目标账户升级并支持回切；
- 使用经典 `/api/v2/spot/account/info` 核对三组凭据属于同一 UID；
- 将 PosiHub 调度器和后端置于维护状态，确认没有同步任务运行；
- 完成 SQLite 一致性备份及 SHA-256 校验，并把备份放在非公开、受权限保护的位置；
- 确认当天尚未产生需要保留的来源账户快照；
- 记录 Bitget 页面上的总权益、现货资产和两类合约仓位作为人工对账基线，不写入仓库。

### 11.2 切换中

1. 由操作人在 Bitget 将账户切到 Advanced Mode；
2. 等待 Bitget 状态完成，不在 `upgrading`/`switching` 时继续；
3. 运行只读 `probe`，核对 UID、权限、账户等级、两类仓位和首期外敞口；
4. `probe` 全绿后运行 `cutover --apply`；
5. 执行单账户同步；
6. 对比 PosiHub 与 Bitget：总权益、资产币种集合、每个 symbol/side 的数量、保证金模式和 PnL；
7. 写一次临时快照并检查总览/绩效口径；
8. 连续手动同步 3 次，确认主键稳定且结果不重复；
9. 恢复后端与调度器。

### 11.3 通过标准

- UID、模式与权限预检无 blocker；
- PosiHub UTA 总权益与 Bitget `usdtEquity` 的差异不超过 `max(1 USDT, 0.1%)`；
- 现货资产集合无遗漏，数量使用 `balance`；
- U 本位和币本位所有非零仓位的 symbol、side 和 qty 一致；
- 当前表只剩目标账户的一份 Bitget 资产池；
- 订单级父 ID 与所有子记录完整；
- 连续 3 次同步成功，且第二、三次不新增重复 current 行；
- 日志中没有密钥、签名、完整 UID 或原始私有响应。

## 12. 回滚

### 12.1 触发条件

出现以下任一情况立即停止调度并回滚或修复前进：

- 总权益超过允许误差；
- 任一非零仓位遗漏、方向错误或数量不一致；
- U 本位/币本位串类；
- 同步产生重复资产、重复仓位或孤儿订单；
- 连续两次同步失败；
- 历史预览可在数据不完整时提交；
- 发现应用调用写接口。

### 12.2 回滚路径

| 所处阶段 | 操作 |
| --- | --- |
| Bitget 尚未切换 | 保持经典账户启用；回退应用提交和 schema 备份即可 |
| Bitget 已切换、数据库未迁移 | 保持服务停止；优先查明 probe 失败原因。只有 Bitget 官方确认可回切时才在平台操作 |
| 数据库已迁移、Bitget 可回切 | 停止服务，恢复切换前数据库备份，部署旧版本，完成 Bitget 回切并确认状态后再启用经典同步 |
| 数据库已迁移、Bitget 暂不可回切 | 不部署旧版经典客户端；保留新代码和备份，禁用定时同步并修复 UTA 读取问题 |

Bitget 当前文档提供“切换到经典账户”及状态查询接口，但 PosiHub 不调用它们。平台回切是否可用属于外部条件，维护窗口前必须人工确认，不能把它当成无条件回滚保证。

来源账户至少保留到 24 小时观察期结束。观察期后可另行、显式清除停用来源账户的旧凭据，但不删除账户及审计数据；该清理不包含在首次 cutover 事务内。

## 13. 完成定义

- [ ] 所有代码变更按第 7 节完成，未引入交易写能力；
- [ ] 依赖固定且 lock/安装结果可复现；
- [ ] schema 和 cutover 脚本默认 dry-run、自动备份、幂等；
- [ ] 第 10 节测试全部通过；
- [ ] 生产数据库副本演练通过并保存脱敏报告；
- [ ] 连接页能显示脱敏 UID、账户模式、等级、持仓模式、权限和 blocker；
- [ ] 首期外敞口可被检测并阻断；
- [ ] 实际切换达到第 11.3 节标准；
- [ ] 24 小时观察期内同步、总览、快照和历史回填无异常；
- [ ] 本地提交完整，未向远程推送。

## 14. 官方参考

- [Bitget UTA 介绍与模式能力](https://www.bitget.com/docs/uta/uta-intro)
- [Bitget 经典 API 升级到 UTA 指南](https://www.bitget.com/api-doc/classic/upgrade-to-uta)
- [Bitget 经典账户信息（v2 UID 核对）](https://www.bitget.com/api-doc/classic/spot/account/Get-Account-Info)
- [Bitget UTA 账户信息与权限](https://www.bitget.com/api-doc/uta/account/Get-Account-Info)
- [Bitget UTA 账户设置](https://www.bitget.com/api-doc/uta/account/Get-Account-Setting)
- [Bitget UTA 账户资产](https://www.bitget.com/api-doc/uta/account/Get-Account)
- [Bitget UTA 当前仓位](https://www.bitget.com/api-doc/uta/trade/Get-Position)
- [Bitget UTA 历史仓位](https://www.bitget.com/api-doc/uta/trade/Get-Position-History)
- [Bitget UTA 订单与成交目录](https://www.bitget.com/docs/catalog/trading/order-management)
- [Bitget UTA 更新日志](https://www.bitget.com/api-doc/uta/changelog)
- [CCXT 4.5.77 PyPI 发布页](https://pypi.org/project/ccxt/4.5.77/)
- [CCXT Bitget 实现](https://github.com/ccxt/ccxt/blob/v4.5.77/python/ccxt/bitget.py)
