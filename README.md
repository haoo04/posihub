# posihub

> 个人交易账户与仓位管理系统。详见 [`docs/trading-account-position-management-dev.md`](docs/trading-account-position-management-dev.md)。

当前版本：后端 MVP 基础骨架（FastAPI + SQLModel + CCXT 4.5.52 + Pydantic 2.12.5）。

## 1. 环境要求

- Python ≥ 3.12
- Windows / macOS / Linux 均可（默认 SQLite，零依赖）

## 2. 后端快速开始

```powershell
# 1) 安装依赖
cd backend
pip install -r requirements.txt

# 2) 生成加密密钥并填入 .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 复制项目根目录 .env.example -> .env，把上面的密钥填到 POSIHUB_ENCRYPTION_KEY

# 3) 初始化数据库 + 写入常用 symbol 映射
cd ..
python -m scripts.init_db
python -m scripts.seed_symbol_mapping

# 4) 启动 API（默认 http://127.0.0.1:8000）
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI 文档：<http://127.0.0.1:8000/docs>。

## 3. 已实现接口（Phase 1 基础）

| Method | Path | 说明 |
| --- | --- | --- |
| GET    | `/health`                              | 健康检查 |
| GET    | `/api/v1/overview`                     | 总资产 / 仓位 / 同步状态汇总 |
| GET/POST | `/api/v1/exchanges`                  | 交易所配置 |
| GET/POST/PATCH/DELETE | `/api/v1/accounts`      | 账户管理（Read-only Key 加密存储） |
| POST   | `/api/v1/accounts/{id}/sync`           | 手动同步单账户 |
| GET    | `/api/v1/positions?view=split\|merged` | 分仓 / 合仓视图 |
| GET    | `/api/v1/pnl?range=30d`                | 日级权益曲线 |
| GET/POST | `/api/v1/snapshots/daily/...`        | 历史快照查询 / 触发 |
| POST   | `/api/v1/manual/snapshot`              | 手动录入 / 模拟账户快照 |
| GET/POST/DELETE | `/api/v1/symbols`             | 统一 Symbol 映射白名单 |

## 4. 目录结构

```
posihub/
  backend/
    app/
      api/            # FastAPI 路由
      core/           # 配置、加密、日志、调度
      db/             # SQLModel 模型与会话
      schemas/        # Pydantic v2 DTO
      services/
        exchange/     # CCXT 只读连接器 + 工厂
        normalize/    # symbol_mapper / normalizer
        aggregate/    # 仓位聚合 / PnL
        sync_service.py
        snapshot_service.py
      main.py
      tests/          # pytest 单元测试
    requirements.txt
    pyproject.toml
  scripts/
    init_db.py
    seed_symbol_mapping.py
  docs/
  .env.example
```

## 5. 测试

```powershell
cd backend
pytest
```

## 6. 安全说明

- API Key / Secret / Passphrase 使用 Fernet（AES128-CBC + HMAC-SHA256）对称加密落库。
- 加密密钥仅存放在 `.env` 中的 `POSIHUB_ENCRYPTION_KEY`，**绝不**提交到仓库。
- 默认 `app_host=127.0.0.1`，仅本机访问；如需暴露请自行配置反向代理与认证。
- 所有 CCXT 调用仅使用 `fetch_balance` / `fetch_positions` / `load_markets`，未启用任何下单/提现接口。
