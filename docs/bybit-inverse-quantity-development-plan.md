# Bybit 币本位反向合约成交数量（USD）优化开发文档

> 状态：待开发
>
> 编写日期：2026-09-23
>
> 本文只定义需求与实施方案，不包含代码实现。

## 1. 结论

可以实现，并且不应只修改输入框名称。

本次采用以下方案：

- 对 **Bybit + 币本位永续账户 + `*-USD-PERP` 合约**，用户和 API 一律使用 Bybit 的成交数量语义，即 **USD 合约数量**。
- 前端新增、编辑、FIFO 平仓、指定配对平仓时均填写 USD，例如 `65 USD`，不再要求用户自行换算为 SOL。
- 数据库现有数量列继续保存“按开仓价折算的结算币数量”，不新增数量列，也不批量改写已有订单数据。
- 后端负责 USD 与内部数量之间的双向换算；前端只负责显示单位和换算预览，不能自行决定最终入库值。
- Bybit 以外的现货、U 本位、Bitget 币本位等现有数量语义保持不变。

选择“边界换算、内部存储不变”的原因是：当前 Bybit 币本位订单已经按 `USD 数量 / 开仓价` 保存。例如已有的 `0.6632653 SOL @ 98` 实际就是约 `65 USD`。保留这一内部表示可以继续复用现有 FIFO、加权均价和 USD 等值盈亏逻辑，变更和历史数据风险最小。

---

## 2. 业务背景与样例

### 2.1 用户提供的 SOLUSD 样例

| 动作 | 成交价 | Bybit 成交数量 | 成交币值 |
| --- | ---: | ---: | ---: |
| 开仓买入 | 98.00 USD/SOL | 65 USD | `65 / 98 = 0.6632653061 SOL` |
| 平仓卖出 | 98.44 USD/SOL | 65 USD | `65 / 98.44 = 0.6603006908 SOL` |

开仓与平仓的 SOL 成交额不同，并不表示只平掉了部分仓位。反向合约固定的是 USD 合约数量 `65`，SOL 等值会随成交价变化。

本例的多头毛盈亏为：

```text
SOL 盈亏
= 65 × (1 / 98.00 - 1 / 98.44)
= 0.0029646153 SOL

按平仓价折算的 USD 等值
= 0.0029646153 × 98.44
= 0.2918367347 USD
```

这里的盈亏不含开仓手续费、平仓手续费和资金费。

### 2.2 字段取值原则

手动录入或将来接入 Bybit 成交历史时，使用以下优先级：

1. 数量使用实际 **Filled Quantity / `cumExecQty` / `execQty`**，单位为 USD 合约数量。
2. 价格使用实际 **Filled Price / `avgPrice` / `execPrice`**。
3. 市价单页面展示的预估“订单额”不能作为成交数量；本例平仓时的 `0.69407367 SOL` 不参与 FIFO 匹配。
4. 部分成交只录入已成交 USD 数量，不能使用原始委托数量。
5. 一个订单包含多笔成交时，首期使用 Bybit 返回的累计成交数量和成交均价；后续若按 execution 导入，再按每笔成交分别汇总。

---

## 3. 现状审计

| 链路 | 当前实现 | 问题 |
| --- | --- | --- |
| 订单新增/编辑 | `PositionOrderModal` 统一要求填写 `open_qty`，界面默认理解为标的币数量 | Bybit SOLUSD 用户必须手算 `65 / 98` |
| FIFO/指定平仓 | `close_qty` 与 `remaining_qty` 直接按同一数值扣减 | 若用户填平仓成交额 `0.66030069 SOL`，无法与开仓记录 `0.6632653 SOL` 精确匹配 |
| 订单未实现盈亏 | `(标记价 - 开仓价) × 内部数量` | 对现有“开仓价折算币量”可以得到正确的 USD 等值，但代码没有声明这一数量语义 |
| 已实现盈亏 | `(平仓价 - 开仓价) × 内部数量` | USD 等值正确；已实现 SOL 盈亏目前可能按当前标记价反推，会随标记价变化 |
| API 仓位同步 | CCXT `contracts` 被直接写入 `positions_current.qty` | Bybit 返回 USD 合约数，而有订单明细时同步后又会被订单折算币量覆盖，单位会来回变化 |
| 合仓名义价值 | 默认 `qty × mark_price` | 对反向合约可能把 USD 合约数量再次乘价格 |
| 页面/CSV | 多数位置只显示“数量” | 无法判断 `65` 是 USD、SOL 还是合约张数 |

当前本地数据也验证了上述表示：`0.6632653 × 98 ≈ 65`。因此仅把输入框标签改为 USD 而不做请求换算，会把 `65` 当成 `65 SOL` 入库，并放大持仓与盈亏约 98 倍。

---

## 4. 目标与非目标

### 4.1 本次目标

- 用户直接按照 Bybit 页面填写 USD 成交数量。
- 新增、编辑、查询、FIFO 平仓、指定配对、配对明细和交易统计中的数量单位一致。
- Bybit API 当前仓位与本地订单明细使用同一内部数量语义，不再在同步后跳变。
- 反向合约的开仓均价、未实现盈亏、已实现盈亏、剩余数量和名义敞口正确。
- 已有 Bybit 币本位订单无需重新录入。
- 其他交易所和账户类型无行为变化。

### 4.2 非目标

- 不在本次实现真实下单。
- 不实现 Bybit 历史订单自动回填；只为后续回填明确数量契约。
- 不把手续费和资金费纳入现有 `realized_pnl`；本次仍展示价格变动产生的毛盈亏。
- 不修改 Bitget、Binance、OKX 币本位数量规则。
- 不把数据库 `float` 全面迁移为 `Decimal`。
- 不重新设计保证金、MMR 或强平价公式。

---

## 5. 适用范围与数量契约

### 5.1 后端判定条件

只有同时满足以下条件才启用本方案：

```text
exchange.name == "bybit"
account.account_type == "coin_perp"
canonical_symbol 的 quote == "USD"
```

不能只根据前端传入的布尔值、账户名称或 symbol 后缀决定。后端必须通过 `position_id -> account -> exchange` 得到权威上下文。

如果账户是 Bybit 币本位，但仓位不是 `*-USD-PERP`，创建/平仓接口应返回明确的 4xx 错误，避免按错误单位静默写入。

### 5.2 三种数量

| 名称 | 例子 | 用途 |
| --- | ---: | --- |
| USD 合约数量 `quote_qty` | `65 USD` | 用户输入、API 请求/响应、FIFO 可平数量、表格和 CSV |
| 开仓折算币量 `entry_base_qty` | `65 / 98 = 0.6632653 SOL` | 当前数据库内部保存和开仓成本计算 |
| 当前/平仓折算币量 `value_base_qty` | `65 / 98.44 = 0.66030069 SOL` | UI 提示、结算币盈亏换算，不作为 FIFO 扣减数量 |

内部保存的 `entry_base_qty` 是记账表示，不等于平仓时实际成交的 SOL 等值。业务界面不得直接暴露它为“成交数量”。

### 5.3 字段语义

本次不新增数据库列，现有字段的内部含义保持不变：

| 数据库字段 | Bybit 币本位内部值 | 对外 API/UI 值 |
| --- | --- | --- |
| `positions_current.qty` | 剩余 USD 数量按平均开仓价折算的币量 | USD 合约数量 |
| `position_orders.open_qty` | 原始 USD 数量按该订单开仓价折算的币量 | USD 合约数量 |
| `position_orders.remaining_qty` | 剩余 USD 数量按该订单开仓价折算的币量 | USD 合约数量 |
| `position_close_executions.close_qty` | 本次各配对订单内部扣减币量之和 | 本次各配对 USD 数量之和 |
| `position_order_matches.matched_qty` | 对应开仓订单的内部扣减币量 | 从该订单扣减的 USD 数量 |
| 各 `realized_pnl` / `unrealized_pnl` | 现有 USDT 等值口径 | USDT 等值；另显示结算币值 |

所有会独立展示数量的响应增加：

```json
{
  "quantity_mode": "quote_contract",
  "quantity_unit": "USD"
}
```

非目标账户返回 `quantity_mode: "base"`，`quantity_unit` 使用其现有标的币单位。请求中不接受客户端自行提交 `quantity_mode`，防止伪造单位。

### 5.4 账户类型稳定性

上述语义依赖账户的交易所和账户类型。已有仓位订单或平仓记录时，不允许直接把账户从 `coin_perp` 修改为其他类型；应先清理/迁移业务数据。交易所本身当前不可在账户编辑接口中修改，保持现状。

---

## 6. 换算与计算规则

设：

- `Q`：USD 合约数量；
- `E`：开仓成交均价；
- `M`：当前标记价；
- `X`：平仓成交均价。

### 6.1 API/UI 与数据库换算

```text
写入内部数量 = Q / E
读取 USD 数量 = 内部数量 × E
某价格下的币值 = Q / price
```

所有换算要求价格大于 0。不能用标记价替代缺失的开仓价，否则后续同步会改变数量。

### 6.2 未实现盈亏

反向合约结算币盈亏：

```text
LONG : pnl_coin = Q × (1 / E - 1 / M)
SHORT: pnl_coin = Q × (1 / M - 1 / E)
```

系统统一 USDT 等值：

```text
pnl_usdt = pnl_coin × M
```

使用内部数量 `Q / E` 时，现有线性计算与上述 USDT 等值完全等价：

```text
LONG: (M - E) × (Q / E) = Q × (M / E - 1)
```

因此无需改写数据库，也无需对已有订单重算 USDT 等值盈亏；但必须增加反向合约单元测试，锁定这一等价关系。

### 6.3 已实现盈亏

```text
LONG : pnl_coin = Q × (1 / E - 1 / X)
SHORT: pnl_coin = Q × (1 / X - 1 / E)
pnl_usdt = pnl_coin × X
```

`PositionOrderMatch.realized_pnl` 继续保存 `pnl_usdt`。展示结算币盈亏时，必须按每条 match 使用其自己的 `close_price` 换算后再求和：

```text
realized_pnl_coin = Σ(match.realized_pnl / match.close_price)
```

不能再用当前标记价反推历史已实现 SOL 盈亏，也不能用一个平均平仓价除总盈亏代替逐笔求和。

### 6.4 平均开仓价

Bybit 反向合约的平均开仓价是按 USD 合约数量计算的调和均价：

```text
average_entry = ΣQ / Σ(Q / E)
```

数据库内部保存 `Q / E`，所以现有的以下计算本身可以得到同一结果：

```text
average_entry
= Σ(entry_base_qty × E) / Σ(entry_base_qty)
= ΣQ / Σ(Q / E)
```

实现时应补充说明与测试，避免后续开发者误把外部 USD 数量直接套入普通算术加权公式。

### 6.5 名义敞口与数量百分比

- Bybit 反向合约的 USD 面值为 `Q`，不能计算成 `Q × mark_price`。
- 当前结算币等值为 `Q / M`。
- 订单页现有盈亏百分比继续表示“毛盈亏 / USD 合约面值”，不命名为 Bybit ROI。
- Bybit ROI 依赖实际保证金、手续费等，本次不模拟。

### 6.6 精度

- 手动记账允许正的小数，不在前端硬编码“必须为整数”。
- 输入步长可默认为 `1` 方便录入，但不能以此拒绝 Bybit 将来允许的合法小数。
- 将来接入市场规格时，以 Bybit `lotSizeFilter.qtyStep` 或 CCXT 市场精度为准。
- 比较和扣减继续使用容差，但容差作用于同一单位；USD 与 SOL 不能共用同一次比较。
- 兼容已有 8 位 SOL 手工数据时，每条订单的 USD 换算容差至少覆盖 `entry_price × 1e-8`；请求与可用量只差该容差时，按全量扣减，避免 `65` 因底层 `64.9999994` 被判为超量。
- API 返回数量时优先按市场 `qtyStep` 归一；无法取得规格时，只把落在上述遗留误差范围内的近整数吸附到整数，不能无条件把所有数量取整。

---

## 7. 交互设计

### 7.1 添加/编辑订单

目标账户中的表单调整为：

- `开仓数量` 改为 `成交数量 (USD)`；
- placeholder 使用 `65`；
- 提示文案：`请填写 Bybit 的 Filled Quantity，不要填写 SOL 成交额`；
- 当数量和开仓价均有效时，显示只读预览：`开仓成交额约 0.66326531 SOL`；
- 编辑已有 `0.6632653 SOL @ 98` 的记录时，输入框显示 `65 USD`，直接保存不能改变实际仓位。

其他账户继续显示原有“开仓数量/买入数量”。

### 7.2 FIFO 平仓

- 字段改为 `平仓成交数量 (USD)`；
- `可平总量` 显示各订单剩余 USD 数量之和；
- 输入 `65`、平仓价 `98.44` 时显示：`平仓成交额约 0.66030069 SOL`；
- 后端按每个开仓订单的开仓价把分配到的 USD 数量换算为内部扣减量，不能用平仓价直接扣减 `remaining_qty`；
- 完全平仓后剩余必须为 `0 USD`，不能因开平币值不同留下 SOL 尾差。

### 7.3 指定配对平仓

- 每个订单行的“剩余”和“本次平仓”均显示/填写 USD；
- 每一行执行 `本次 USD / 该行开仓价` 后扣减内部数量；
- 所有行的 USD 分配之和必须等于本次 `close_qty`；
- 已实现盈亏按每一行自己的开仓价计算后求和。

### 7.4 表格、移动端和导出

以下位置必须显示明确单位，不能只写“数量”：

- 分仓和合仓仓位；
- 持仓中订单与历史订单；
- 配对记录；
- 绩效页平仓明细；
- 每日仓位快照；
- 对应 CSV 导出。

建议主值显示 `65 USD`，订单详情下可用次要文本显示 `≈ 0.66326531 SOL @ 开仓价`。CSV 增加独立的 `数量单位` 列，避免把单位拼进数值列。

---

## 8. 后端设计

### 8.1 集中数量上下文

在现有 `pnl_calculator.py` 中增加少量纯函数，避免新增无必要的框架层：

- 判断是否为本次目标的 Bybit 反向仓位；
- `quote_qty -> entry_base_qty`；
- `entry_base_qty -> quote_qty`；
- 计算某价格下的结算币等值；
- 计算反向合约原生币盈亏。

业务路由和服务使用同一组函数，禁止前端、路由、FIFO 服务各写一套公式。

### 8.2 交易所同步

CCXT 仓位中的 `contracts` 是合约数。对目标仓位：

```text
Q = contracts × contract_size
internal_qty = Q / entry_price
```

当前 SOLUSD 的 `contract_size` 为 1 时，`contracts` 与 USD 数量相同，但实现仍应保留 `contract_size`，不能把“1”写死。

处理要求：

- `entry_price <= 0` 时不做猜测性换算，记录明确错误并保留上一条有效仓位；
- 同步写入后再由订单明细刷新仓位时，两边内部单位必须相同；
- API 原始 `unrealizedPnl` 继续只在同步边界转换一次为 USDT 等值。

### 8.3 订单 API

对目标仓位，现有字段名保持不变，但 HTTP 契约改为 USD：

- `POST/PATCH open_qty`：外部 USD，入库前除以最终 `entry_price`；
- `PATCH remaining_qty`：外部 USD，入库前除以最终 `entry_price`；
- `GET open_qty/remaining_qty`：内部数量乘该订单 `entry_price`；
- 新增 `quantity_mode` 和 `quantity_unit` 响应字段。

当 PATCH 同时修改价格和数量时，统一使用新价格换算。只修改价格时，先保留原 USD 数量，再根据新价格重算内部数量，避免一次改价意外改变合约面值。

### 8.4 平仓服务

FIFO 的目标账户分配算法：

```text
remaining_usd = request.close_qty

for order in FIFO order:
    order_available_usd = order.remaining_qty × order.entry_price
    consume_usd = min(order_available_usd, remaining_usd)
    consume_internal = consume_usd / order.entry_price
    apply existing match with consume_internal
    remaining_usd -= consume_usd
```

指定配对使用相同的逐行换算。

数据库 execution/match 仍写内部数量；响应序列化时通过 matches 还原：

```text
match_usd = matched_qty × open_price
execution_usd = Σmatch_usd
```

若历史 execution 缺少 match，不能静默伪造精确 USD 数量；响应应使用明确的兼容回退并记录警告，数据审计中列出该记录。

### 8.5 仓位与合仓

- 分仓响应的 USD 数量为 `position.qty × position.entry_price`。
- Bybit 反向仓位的 `notional` 等于 USD 数量，不再乘标记价。
- 合仓必须先把每条目标仓位还原为 `Q = qty × entry_price`，再按带方向的 USD 数量净额聚合；多空不能直接按内部折算币量相减。
- 合仓净额为多头时，均价只按多头各腿计算 `ΣQ / Σ(Q / E)`；净额为空头时同理使用空头各腿。这与当前“使用胜出方向均价”的行为一致。
- 不同 `quantity_mode` 的仓位不能直接相加；合仓分组至少使用 `canonical_symbol + quantity_mode + quantity_unit`。
- 前端行键同步包含 quantity mode，避免同 symbol 的两行互相覆盖。
- 实时价格仍可按 canonical symbol 共用，不使用不同单位的 qty 做价格权重。

### 8.6 绩效与快照

- 绩效平仓列表从 matches 汇总外部 USD `close_qty`；按数量排序也必须使用该外部值。
- 持仓时长的权重对目标账户使用匹配 USD 数量，而不是内部 SOL 数量。
- 新写入的仓位快照保存内部数量，读取和导出时转换为 USD 并带 `quantity_unit`。
- 手动快照页选择目标账户后，仓位数量输入同样切换为 USD；后端入库前换算。

---

## 9. API 示例

### 9.1 新增开仓订单

请求：

```json
{
  "position_id": 21,
  "source": "manual",
  "source_order_id": "example-open",
  "open_qty": 65,
  "entry_price": 98,
  "leverage": 1
}
```

响应中的业务数量仍为 USD：

```json
{
  "position_id": 21,
  "open_qty": 65,
  "remaining_qty": 65,
  "entry_price": 98,
  "quantity_mode": "quote_contract",
  "quantity_unit": "USD"
}
```

数据库内部 `open_qty` 和 `remaining_qty` 约为 `0.6632653061`。

### 9.2 FIFO 全平

请求：

```json
{
  "close_qty": 65,
  "close_price": 98.44,
  "source": "manual"
}
```

预期：

- API 返回 `execution.close_qty = 65`、`quantity_unit = "USD"`；
- 订单 `remaining_qty = 0`；
- 毛已实现盈亏约 `0.0029646153 SOL / 0.2918367347 USDT`；
- 内部 match 扣减约 `0.6632653061`，而 UI 的平仓成交额提示约为 `0.6603006908 SOL`。

---

## 10. 既有数据与上线方案

### 10.1 订单数据不迁移

现有 Bybit 币本位订单已按 `USD / 开仓价` 保存，直接满足新内部契约。以下表不做批量乘价迁移：

- `position_orders`；
- `position_order_matches`；
- `position_close_executions`。

如果把这些值改写为 USD，现有线性等价盈亏和平均开仓价都会被破坏，因此明确禁止这样做。

### 10.2 当前仓位审计

上线前执行只读审计：

1. 找出 Bybit `coin_perp` 的所有 `*-USD-PERP` 仓位。
2. 有订单明细的仓位，用订单重新计算内部 qty、均价和未实现盈亏。
3. 无订单明细且来源为 API 的仓位，在首次新版本同步时按 `contracts × contract_size / entry_price` 覆盖。
4. 无有效开仓价或来源为 manual 的可疑行只报告，不自动猜测。
5. 审计 execution 是否全部有 match；缺失 match 的记录必须列出。
6. 审计历史仓位快照是否存在混合单位。截至 2026-09-23，本地数据库没有 Bybit 币本位仓位快照；若部署库发现有候选行，应先单独确认再迁移。

基线方案不新增一次性迁移脚本；先备份 SQLite，再部署并强制同步一次 Bybit 币本位账户即可。只有审计发现无法通过同步或订单重算修复的数据时，才按现有 `DataMigration` 模式补充幂等修复脚本，默认 dry-run、apply 前自动备份。

### 10.3 发布顺序

1. 停止定时同步和手动录入。
2. 备份 SQLite 数据库。
3. 运行只读审计并保存结果。
4. 部署后端数量换算与 API 响应。
5. 部署前端，避免旧前端把 USD 响应继续当 SOL 展示。
6. 强制同步一次 Bybit 币本位账户。
7. 用本文 65 USD 样例做新增、查询、全平的 smoke test。
8. 恢复定时同步。

前后端必须同一维护窗口发布。本次对 Bybit 币本位的 `open_qty`、`remaining_qty`、`close_qty` HTTP 语义属于上下文内的破坏性变更，任何外部调用方都需要同步改为 USD。

### 10.4 回滚

订单与 match 数据没有改写，因此代码可以回滚。回滚后应再次同步 Bybit 币本位账户，使无订单明细的 `positions_current.qty` 恢复旧版本预期；在确认前保持录入暂停。

---

## 11. 预计修改范围

### 后端

| 文件 | 计划修改 |
| --- | --- |
| `backend/app/services/pnl_calculator.py` | 增加目标判定、数量换算和反向原生币盈亏纯函数 |
| `backend/app/services/normalize/normalizer.py` | 将 Bybit inverse 的 contracts/contract size 归一为内部开仓折算币量 |
| `backend/app/api/routes_position_orders.py` | 请求写入换算、响应数量换算、准确的原生币已实现盈亏 |
| `backend/app/services/position_order_close.py` | FIFO/指定配对按 USD 分配、按开仓价转换后扣减 |
| `backend/app/api/routes_positions.py` | 暴露 quantity metadata，转换分仓/合仓数量和名义敞口 |
| `backend/app/schemas/position.py`、`position_order.py`、`snapshot.py` | 为独立展示数量的 DTO 增加 mode/unit 元数据 |
| `backend/app/services/aggregate/position_aggregator.py` | 禁止混合单位聚合，修正 Bybit inverse notional |
| `backend/app/services/live_prices.py` | 合仓实时价格不再用混合单位数量加权 |
| `backend/app/services/performance/trades.py` | 输出/排序 USD 平仓量并修正持仓时长权重 |
| `backend/app/api/routes_manual.py`、快照 schema/routes | 手动仓位输入和历史快照输出使用外部 USD 语义 |
| `backend/app/api/routes_accounts.py` | 有订单历史时阻止改变账户类型 |

### 前端

| 文件 | 计划修改 |
| --- | --- |
| `frontend/src/api/types.ts` | 增加 `quantity_mode`、`quantity_unit` 类型字段 |
| `frontend/src/pages/PositionsPage.tsx` | 传递数量上下文，分仓/合仓显示单位 |
| `frontend/src/components/PositionOrderModal.tsx` | USD 输入、说明和 SOL 换算预览 |
| `frontend/src/components/PositionCloseFifoModal.tsx` | USD 可平量、输入和关闭币值预览 |
| `frontend/src/components/PositionCloseSpecifiedModal.tsx` | 各订单按 USD 分配 |
| `frontend/src/components/PositionOrdersTable.tsx` | 桌面/移动端数量统一显示 USD |
| `frontend/src/components/PositionOrderMatchesPanel.tsx` | 匹配数量显示单位 |
| `frontend/src/pages/PerformancePage.tsx` | 平仓数量和 CSV 增加单位 |
| `frontend/src/pages/ManualEntryPage.tsx`、`SnapshotsPage.tsx` | Bybit 币本位仓位输入/快照显示单位 |

不新增数据库表或列。

---

## 12. 测试计划

### 12.1 后端单元测试

1. 只有 `bybit + coin_perp + USD quote` 命中 quote-contract 模式。
2. `65 USD @ 98` 写入内部为 `0.6632653061`，读取恢复为 `65 USD`。
3. 已有内部记录通过 GET 显示为 USD，编辑后直接保存不漂移。
4. `65 USD @ 98.44` FIFO 全平后剩余为 0。
5. 上述全平毛盈亏为约 `0.0029646153 SOL / 0.2918367347 USDT`。
6. 部分平仓 `30 USD` 后准确剩余 `35 USD`。
7. 多开仓价 FIFO：先耗尽第一笔 USD，再消耗第二笔；内部扣减分别按各自开仓价换算。
8. 指定配对中各 leg 的 USD 之和必须等于总 close qty。
9. 多头和空头的反向原生币盈亏方向正确。
10. 多订单平均开仓价使用反向合约调和均价结果。
11. 已实现原生币盈亏按每条 match 的平仓价求和，不受当前 mark price 变化影响。
12. API 同步的 `contracts × contract_size / entry_price` 与订单重算结果一致。
13. Bybit U 本位、Bitget 币本位、现货和模拟账户结果保持不变。
14. 合仓不混加不同 quantity mode；Bybit inverse 按 USD 数量净额聚合，等量多空能正确抵消，notional 等于净 USD 合约数量。
15. 开仓价为 0、负数量、超量平仓和单位上下文异常均被后端拒绝。
16. 旧记录 `0.6632653 × 98 = 64.9999994` 能显示并全平为 `65 USD`，真正超过容差的请求仍被拒绝。

### 12.2 前端测试

1. 目标账户显示 `成交数量 (USD)`，其他账户维持原标签。
2. 表单填写 `65` 与 `98` 时显示约 `0.66326531 SOL`。
3. 平仓填写 `65` 与 `98.44` 时显示约 `0.66030069 SOL`。
4. 桌面表格、移动端卡片、指定配对和 match 展开行均显示 USD。
5. 编辑已有订单时初始值为 65 而非 0.6632653。
6. 绩效与快照 CSV 数值列保持纯数字，并另有单位列。

### 12.3 回归命令

```powershell
python -m pytest backend/tests
npm.cmd --prefix frontend run test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

---

## 13. 验收标准

- [ ] Bybit 币本位 SOLUSD 添加订单时可直接填写 `65 USD @ 98.00`。
- [ ] 保存后订单表显示 `65 USD`，并可看到约 `0.66326531 SOL` 的开仓成交额。
- [ ] FIFO 或指定配对可直接填写 `65 USD @ 98.44` 并一次全平。
- [ ] 全平后剩余数量为 `0 USD`，不存在由开平 SOL 成交额不同造成的尾仓。
- [ ] 毛已实现盈亏约为 `0.0029646153 SOL / 0.2918367347 USDT`。
- [ ] 改变当前标记价不会改变上述已实现 SOL 盈亏。
- [ ] API 同步前后，仓位和订单数量不会在 `65` 与 `0.663...` 之间跳变。
- [ ] 分仓、合仓、订单、配对、绩效、快照及 CSV 的数量均带明确单位。
- [ ] 已有 Bybit 币本位订单无需手工修改即可按 USD 正确显示。
- [ ] Bitget 币本位及其他账户的数量、FIFO 和盈亏测试全部保持通过。
- [ ] 未新增数据库列，部署前完成备份和只读数据审计。

---

## 14. 风险与控制

| 风险 | 控制措施 |
| --- | --- |
| 只改标签导致 65 被当成 65 SOL | 后端做权威换算，前端不直接决定入库单位 |
| 平仓时用 `Q / X` 扣减开仓记录造成尾差 | FIFO 始终按每条订单的 `Q / E` 扣减，`Q / X` 仅用于展示和结算 |
| 旧前端与新后端单位不一致 | 同一维护窗口发布并暂停录入 |
| 同 symbol 的不同交易所数量单位被直接合并 | 合仓 key 包含 quantity mode/unit |
| 已实现币盈亏随 mark price 变化 | 按每条 match 的 close price 换算 |
| 市价单预估订单额被误录 | UI 明确提示只填 Filled Quantity，文档规定字段优先级 |
| 账户类型被修改后历史数量失去语义 | 有订单/平仓历史时禁止直接修改 account type |
| 浮点换算出现 `64.9999994` | 集中格式化与容差处理，不无条件整数化 |

---

## 15. 实施顺序与完成定义

1. 先补数量上下文、换算公式及后端单元测试。
2. 修正同步归一化和订单 API 序列化。
3. 修改 FIFO/指定配对与已实现原生币盈亏。
4. 修正分仓、合仓、绩效和快照读取。
5. 完成前端所有输入与展示入口。
6. 完成数据审计、全量测试和 65 USD smoke test。

完成定义：第 13 节全部通过，所有自动化测试通过，部署审计无未解释的混合单位记录，且本次样例可以从新增到全平完整复现。

---

## 16. 参考资料

- [Bybit：反向永续及交割合约盈亏计算](https://www.bybit.com/en/help-center/article/Profit-Loss-calculations-Inverse-Contracts)
- [Bybit V5：订单历史字段](https://bybit-exchange.github.io/docs/v5/order/order-list)
- [Bybit V5：成交历史字段](https://bybit-exchange.github.io/docs/v5/order/execution)
- [Bybit V5：合约规格与 qtyStep](https://bybit-exchange.github.io/docs/v5/market/instrument)
- [CCXT Manual：合约数量、contractSize 与反向合约](https://github.com/ccxt/ccxt/wiki/Manual)
