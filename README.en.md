# posihub

[English](README.en.md) | [简体中文](README.md)

posihub is a local-first application for managing personal accounts, positions, PnL, and trading performance across multiple exchanges. Its backend uses FastAPI, SQLModel, SQLite, and CCXT; its frontend uses React, TypeScript, Vite, Ant Design, and ECharts.

> posihub is designed for read-only synchronization, portfolio visualization, and local trade accounting. It never submits orders, cancellations, or withdrawal requests to an exchange.

## Features

- **Accounts and exchanges**: manage spot, USDT-margined perpetual, coin-margined perpetual, delivery futures, funding, and simulated accounts; encrypt API credentials; synchronize one/all accounts manually or on a schedule.
- **Connection status**: test an exchange API through its read-only balance endpoint and retain the status, latency, and sanitized error details.
- **Positions and prices**: switch between spot/derivatives and split/merged views; aggregate positions by canonical symbol; refresh public prices every 15 seconds while retaining the latest usable price on failure.
- **Orders and local accounting**: record position-order lots, perform local FIFO or specified-lot close accounting, and calculate realized/unrealized PnL. These operations do not execute trades at an exchange.
- **History backfill**: preview, validate, deduplicate, and then commit historical Bitget orders.
- **Snapshots and analytics**: create daily snapshots automatically or manually; inspect equity, PnL, drawdown, win rate, Profit Factor, Calmar ratio, streaks, and multidimensional performance.
- **Data maintenance**: manage symbol mappings, enter simulated/historical snapshots, and export snapshots, symbol mappings, and trade details as CSV.
- **User experience**: responsive desktop/mobile layouts; the application shell, Overview page, and Settings page can switch between Simplified Chinese and English.

Exchanges are configured with a CCXT exchange id. The bundled symbol seeds focus on Binance, Bybit, Bitget, and OKX. API-based historical-order backfill currently supports Bitget only.

## Technology

| Layer | Main technology |
| --- | --- |
| Backend | Python 3.12+, FastAPI 0.115, Pydantic 2, SQLModel / SQLAlchemy |
| Exchanges and jobs | CCXT 4.5, APScheduler 3.10 |
| Data and security | SQLite, Fernet encryption (`cryptography`) |
| Frontend | React 18, TypeScript 5.6, Vite 5, Ant Design 5 |
| Data fetching and charts | TanStack Query 5, Axios, ECharts 5 |
| Tests | pytest, Vitest |

## Quick start

### Requirements

- Python 3.12+
- Node.js 18+ and npm
- PowerShell 7 (used by the examples below)

On macOS or Linux, replace `npm.cmd` with `npm` in the examples.

### 1. Install dependencies

Run these commands from the repository root:

```powershell
python -m pip install -r backend/requirements.txt
npm.cmd install
npm.cmd --prefix frontend install
```

The root Node.js dependency is only used to start both services together. Frontend dependencies are installed under `frontend/`.

### 2. Configure the environment

```powershell
Copy-Item .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the generated key into the root `.env` file:

```dotenv
POSIHUB_ENCRYPTION_KEY=paste-the-generated-key-here
```

This key encrypts exchange credentials. Keep an existing key safe: credentials already stored in the database cannot be decrypted after the key is changed or lost.

### 3. Initialize local data

```powershell
python -m scripts.init_db
python -m scripts.seed_symbol_mapping
```

Both commands are idempotent. Backend startup also creates missing tables automatically; the seed command adds common exchange symbol mappings.

### 4. Start the full application

```powershell
npm.cmd run dev
```

- Frontend: <http://127.0.0.1:5173>
- API: <http://127.0.0.1:8000>
- OpenAPI: <http://127.0.0.1:8000/docs>

You can also start the services in separate terminals:

```powershell
# Terminal 1
Set-Location backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
Set-Location frontend
npm.cmd run dev
```

## Main configuration

The backend reads the root `.env` file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./posihub.db` | Relative SQLite paths are resolved under `backend/` |
| `POSIHUB_ENCRYPTION_KEY` | empty | Credential-encryption key; the scheduler stays disabled when empty |
| `APP_TIMEZONE` | `Asia/Shanghai` | Scheduler timezone |
| `SYNC_INTERVAL_MINUTES` | `5` | Automatic synchronization interval |
| `SYNC_MAX_WORKERS` | `4` | Maximum concurrent account synchronizations |
| `DAILY_SNAPSHOT_TIME` | `23:55` | Daily snapshot time (`HH:MM`) |
| `CORS_ALLOW_ORIGINS` | local frontend URLs | Comma-separated CORS origins |
| `ENABLE_POSITION_ORDER_EDIT` | `true` | Enables editing local position orders |
| `SPOT_DUST_THRESHOLD_USD` | `0.01` | USD threshold for ignoring spot dust balances |

`VITE_API_BASE_URL` is optional on the frontend. When it is unset, the Vite development server proxies `/api` and `/health` to `http://127.0.0.1:8000`. See [frontend/README.en.md](frontend/README.en.md).

## API overview

This table lists the main resources only. OpenAPI is the source of truth for request parameters and complete models.

| Resource | Main paths | Purpose |
| --- | --- | --- |
| Health and overview | `/health`, `/api/v1/overview` | Service health, equity, and synchronization summary |
| Exchanges and accounts | `/api/v1/exchanges`, `/api/v1/accounts` | Exchange/account management and manual synchronization |
| Connection tests | `/api/v1/exchange-connections` | Inspect and test read-only API connections |
| Positions and prices | `/api/v1/positions`, `/api/v1/positions/prices` | Split/merged positions, spot/derivatives, and public prices |
| Local orders | `/api/v1/position-orders`, `/api/v1/positions/{id}/close-*` | Order lots and local close accounting |
| History backfill | `/api/v1/accounts/{id}/history-import/*` | Bitget preview and commit workflow |
| PnL and performance | `/api/v1/pnl`, `/api/v1/performance/*` | Equity, drawdown, and trading statistics |
| Snapshots and manual entry | `/api/v1/snapshots/*`, `/api/v1/manual/snapshot` | Query, create, and backfill daily snapshots |
| Symbol mappings | `/api/v1/symbols` | Exchange-symbol normalization settings |

## Repository layout

```text
posihub/
├─ backend/
│  ├─ app/
│  │  ├─ api/                 # FastAPI routes
│  │  ├─ core/                # Configuration, encryption, logging, scheduler
│  │  ├─ db/                  # SQLModel models and sessions
│  │  ├─ schemas/             # API DTOs
│  │  └─ services/            # Sync, prices, backfill, PnL, and analytics
│  ├─ tests/
│  └─ requirements.txt
├─ frontend/
│  ├─ src/api/                # Axios, React Query hooks, and types
│  ├─ src/components/
│  ├─ src/i18n/
│  ├─ src/pages/
│  └─ src/theme/
├─ scripts/                   # Initialization, symbol seeds, and data repair
├─ docs/                      # Product/development documentation
└─ .env.example
```

## Verification

```powershell
Set-Location backend
python -m pytest

Set-Location ..\frontend
npm.cmd run test
npm.cmd run build
```

## Security and deployment boundaries

- Grant exchange API keys only the minimum permissions required to read balances, positions, and history. Never grant trading or withdrawal permissions.
- API keys, secrets, and passphrases are encrypted with Fernet before being stored. The API returns only a masked API key.
- Live prices come from public ticker requests and only overlay the UI; they are not written to positions, balances, or snapshots.
- The application has no built-in user authentication and listens on `127.0.0.1` by default. For remote access, use HTTPS, a reverse proxy, and access controls instead of exposing the API directly.
- Data is stored in `backend/posihub.db` by default. Back up the database before repair or migration operations.

## Further documentation

- [Frontend guide](frontend/README.en.md)
- [Trading account and position development notes (Chinese)](docs/trading-account-position-management-dev.md)
