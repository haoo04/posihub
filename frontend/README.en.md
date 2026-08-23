# posihub frontend

[English](README.en.md) | [简体中文](README.md) | [Project overview](../README.en.md)

The posihub frontend is a responsive trading-account and position dashboard built with React 18, TypeScript, Vite 5, Ant Design 5, TanStack Query, and ECharts.

## Routes

| Path | Functionality |
| --- | --- |
| `/overview` | Total equity, unrealized/realized PnL, position count, equity trend, allocation, and main positions |
| `/accounts` | Add exchanges and real/simulated accounts, synchronize one/all accounts, delete accounts, and preview/commit Bitget history backfills |
| `/positions` | Spot/derivatives and split/merged views, search, 15-second public-price refresh, order lots, and local close accounting |
| `/pnl` | 7/30/90/365-day equity and unrealized-PnL charts |
| `/performance` | Account filters, equity/drawdown, win rate, Profit Factor, Calmar, breakdowns, and exportable closed-trade details |
| `/snapshots` | Query account/position snapshots by date and account, create a snapshot now, and export CSV |
| `/symbols` | Search, filter, enable, edit, delete, and export symbol mappings |
| `/manual` | Backfill account, balance, and position snapshots for simulated accounts or historical data |
| `/settings` | Switch language, check backend health, test exchange APIs, trigger a snapshot, and open maintenance pages |

FIFO and specified-lot closes on the Positions page only update posihub's local accounting data. They do not submit orders to an exchange.

## Local development

### Requirements

- Node.js 18+
- npm
- A running posihub backend (default: `http://127.0.0.1:8000`)

### Install and start

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Open <http://127.0.0.1:5173>.

No frontend `.env` file is required by default: browser requests use same-origin paths, and Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`.

To have the browser call another API URL directly, copy and edit the example:

```powershell
Copy-Item .env.example .env
```

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

When this variable is set, ensure the backend's `CORS_ALLOW_ORIGINS` contains the frontend origin. `VITE_*` values are embedded in production assets; only put a public API address here, never a secret.

See the [root README](../README.en.md) for full-stack installation and the combined development command.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm.cmd run dev` | Start the Vite development server (`127.0.0.1:5173`) |
| `npm.cmd run build` | Run the TypeScript project build and create production assets |
| `npm.cmd run preview` | Preview the production build locally |
| `npm.cmd run test` | Run the Vitest suite once |
| `npm.cmd run test:watch` | Run Vitest in watch mode |
| `npm.cmd run lint` | Run ESLint on TypeScript/TSX; ESLint is not currently pinned and must be available in the environment |

On macOS or Linux, replace `npm.cmd` with `npm`.

## Data-fetching behavior

- `src/api/client.ts` creates the Axios client and exposes a backend `detail` as the displayable error message.
- TanStack Query uses a global 30-second `staleTime` and does not refetch on window focus by default.
- The account list is prefetched at startup so position and manual-entry pages can resolve account names immediately.
- Position prices use a separate policy: a 10-second stale time, polling every 15 seconds while the page is visible, and refresh on window focus.
- Live prices only overlay the current page's price and merged notional values. Failures retain query-cached or persisted position prices and never write to the database.

## Internationalization

The frontend uses a lightweight `LocaleContext` and typed message object without an additional i18n dependency:

- supports `zh-CN` and `en`, with Simplified Chinese as the default;
- persists the selection under `posihub-locale` in browser `localStorage`;
- synchronizes the Ant Design locale, dayjs formatting, `document.documentElement.lang`, and page title;
- falls back to Simplified Chinese when an English message is missing.

Translations currently cover application navigation and status, common async states, the Overview page, and the Settings page. Accounts, Positions, PnL, Performance, Snapshots, Symbol Mapping, and Manual Entry still primarily use Chinese business copy.

## Responsive design and visual system

- Below `768px`, the sidebar becomes a left Drawer that closes after navigation.
- Page actions, filters, and forms stack on narrow screens; wide tables use horizontal scrolling or card views.
- Create Account uses a bottom Drawer on mobile; charts, segmented controls, and page spacing adapt at breakpoints.
- Ant Design tokens and the `posi-light` ECharts theme share a navy primary color, sky-blue accent, gain green, and loss red.
- Numeric values and prices use monospaced fallbacks and tabular figures for alignment.

## Source layout

```text
frontend/
├─ src/
│  ├─ api/          # Axios client, React Query hooks, API types
│  ├─ components/   # Layout, tables, modals, and shared display components
│  ├─ hooks/        # Responsive hooks
│  ├─ i18n/         # LocaleContext and Chinese/English messages
│  ├─ pages/        # Route pages
│  ├─ styles/       # Global styles and mobile rules
│  ├─ theme/        # Ant Design and ECharts themes
│  ├─ utils/        # Formatting, CSV, and order-calculation utilities
│  ├─ App.tsx       # Route table
│  └─ main.tsx      # React providers and application entry point
├─ .env.example
├─ package.json
└─ vite.config.ts
```

## Verification

```powershell
Set-Location frontend
npm.cmd run test
npm.cmd run build
```
