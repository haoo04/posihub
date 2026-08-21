import { useMemo, useState } from "react";
import {
  Button,
  Card,
  DatePicker,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { DownloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { PageHeader } from "@/components/PageHeader";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import { PnlText } from "@/components/PnlText";
import { SideTag } from "@/components/SideTag";
import {
  useAccounts,
  useAccountSnapshots,
  usePositionSnapshots,
  useRunDailySnapshot,
} from "@/api/hooks";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { exportCsv } from "@/utils/csv";
import { fmtMoney, fmtPrice, fmtQty } from "@/utils/format";
import type { AccountSnapshot, PositionSnapshot } from "@/api/types";

const { Text } = Typography;
const { RangePicker } = DatePicker;

type Kind = "accounts" | "positions";

export function SnapshotsPage() {
  const { isMobile } = useBreakpoint();
  const [kind, setKind] = useState<Kind>("accounts");
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>([
    dayjs().subtract(30, "day"),
    dayjs(),
  ]);
  const [accountId, setAccountId] = useState<number | undefined>(undefined);

  const accounts = useAccounts();
  const runSnapshot = useRunDailySnapshot();

  const params = useMemo(
    () => ({
      start: range?.[0]?.format("YYYY-MM-DD"),
      end: range?.[1]?.format("YYYY-MM-DD"),
      account_id: accountId,
    }),
    [range, accountId]
  );

  const accountSnaps = useAccountSnapshots(params);
  const positionSnaps = usePositionSnapshots(params);

  const accountName = useMemo(
    () => new Map((accounts.data ?? []).map((a) => [a.id, a.account_name])),
    [accounts.data]
  );

  const accountOptions = useMemo(
    () =>
      (accounts.data ?? []).map((a) => ({
        value: a.id,
        label: `${a.account_name}${a.is_simulated ? "（模拟）" : ""}`,
      })),
    [accounts.data]
  );

  const onRun = async () => {
    try {
      const res = await runSnapshot.mutateAsync();
      message.success(
        `已生成快照：账户 ${res.accounts_written}，仓位 ${res.positions_written}`
      );
    } catch (e) {
      message.error((e as Error).message ?? "触发失败");
    }
  };

  const accountColumns: ColumnsType<AccountSnapshot> = [
    { title: "日期", dataIndex: "snapshot_date", render: (v: string) => v },
    {
      title: "账户",
      dataIndex: "account_id",
      render: (v: number) => accountName.get(v) ?? `#${v}`,
    },
    { title: "资产", dataIndex: "asset", render: (v: string) => <Tag>{v}</Tag> },
    {
      title: "总权益",
      dataIndex: "total_equity",
      align: "right" as const,
      render: (v: number) => (
        <span className="posi-numeric">{fmtMoney(v)}</span>
      ),
    },
    {
      title: "未实现盈亏",
      dataIndex: "total_unrealized_pnl",
      align: "right" as const,
      render: (v: number) => <PnlText value={v} suffix="USDT" />,
    },
    {
      title: "可用",
      dataIndex: "total_available",
      align: "right" as const,
      render: (v: number) => (
        <span className="posi-numeric">{fmtMoney(v)}</span>
      ),
    },
    {
      title: "来源",
      dataIndex: "source",
      render: (v: string) => <Tag>{v}</Tag>,
    },
  ];

  const positionColumns: ColumnsType<PositionSnapshot> = [
    { title: "日期", dataIndex: "snapshot_date", render: (v: string) => v },
    {
      title: "账户",
      dataIndex: "account_id",
      render: (v: number) => accountName.get(v) ?? `#${v}`,
    },
    {
      title: "合约",
      dataIndex: "canonical_symbol",
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "方向",
      dataIndex: "side",
      render: (v: PositionSnapshot["side"]) => <SideTag side={v} />,
    },
    {
      title: "数量",
      dataIndex: "qty",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    },
    {
      title: "开仓价",
      dataIndex: "entry_price",
      align: "right" as const,
      render: (v: number) => (
        <span className="posi-numeric">{fmtPrice(v)}</span>
      ),
    },
    {
      title: "标记价",
      dataIndex: "mark_price",
      align: "right" as const,
      render: (v: number) => (
        <span className="posi-numeric">{fmtPrice(v)}</span>
      ),
    },
    {
      title: "未实现盈亏",
      dataIndex: "unrealized_pnl",
      align: "right" as const,
      render: (v: number) => <PnlText value={v} suffix="USDT" />,
    },
  ];

  const isAccounts = kind === "accounts";
  const query = isAccounts ? accountSnaps : positionSnaps;

  const onExport = () => {
    const stamp = new Date().toISOString().slice(0, 10);
    if (isAccounts) {
      exportCsv<AccountSnapshot>(
        `account-snapshots-${stamp}.csv`,
        [
          { header: "日期", value: (r) => r.snapshot_date },
          { header: "账户", value: (r) => accountName.get(r.account_id) ?? r.account_id },
          { header: "资产", value: (r) => r.asset },
          { header: "总权益", value: (r) => r.total_equity },
          { header: "未实现盈亏", value: (r) => r.total_unrealized_pnl },
          { header: "可用", value: (r) => r.total_available },
          { header: "来源", value: (r) => r.source },
        ],
        accountSnaps.data ?? []
      );
    } else {
      exportCsv<PositionSnapshot>(
        `position-snapshots-${stamp}.csv`,
        [
          { header: "日期", value: (r) => r.snapshot_date },
          { header: "账户", value: (r) => accountName.get(r.account_id) ?? r.account_id },
          { header: "合约", value: (r) => r.canonical_symbol },
          { header: "方向", value: (r) => r.side },
          { header: "数量", value: (r) => r.qty },
          { header: "开仓价", value: (r) => r.entry_price },
          { header: "标记价", value: (r) => r.mark_price },
          { header: "未实现盈亏", value: (r) => r.unrealized_pnl },
        ],
        positionSnaps.data ?? []
      );
    }
  };

  const exportDisabled = isAccounts
    ? !(accountSnaps.data?.length ?? 0)
    : !(positionSnaps.data?.length ?? 0);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="历史快照"
        description="按日期与账户回查每日权益与仓位快照，可导出 CSV"
        extra={
          <>
            <Button
              icon={<ThunderboltOutlined />}
              loading={runSnapshot.isPending}
              onClick={onRun}
            >
              立即生成快照
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={onExport}
              disabled={exportDisabled}
            >
              导出 CSV
            </Button>
          </>
        }
      />

      <Space wrap size={12}>
        <Segmented
          value={kind}
          onChange={(v) => setKind(v as Kind)}
          options={[
            { label: "账户快照", value: "accounts" },
            { label: "仓位快照", value: "positions" },
          ]}
        />
        <RangePicker
          value={range}
          onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)}
          allowClear={false}
        />
        <Select
          allowClear
          placeholder="全部账户"
          value={accountId}
          onChange={(v?: number) => setAccountId(v)}
          options={accountOptions}
          style={{ width: 200 }}
        />
      </Space>

      <Card bodyStyle={{ padding: 0 }} style={{ borderRadius: 12 }}>
        <AsyncBoundary
          loading={query.isLoading}
          error={query.error}
          empty={
            isAccounts
              ? !accountSnaps.data?.length
              : !positionSnaps.data?.length
          }
          emptyText="该区间暂无快照，可点「立即生成快照」或调整日期"
        >
          {isAccounts ? (
            <Table<AccountSnapshot>
              rowKey="id"
              columns={accountColumns}
              dataSource={accountSnaps.data ?? []}
              loading={accountSnaps.isFetching && !accountSnaps.isLoading}
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              size={isMobile ? "small" : "middle"}
              scroll={isMobile ? { x: 720 } : undefined}
            />
          ) : (
            <Table<PositionSnapshot>
              rowKey="id"
              columns={positionColumns}
              dataSource={positionSnaps.data ?? []}
              loading={positionSnaps.isFetching && !positionSnaps.isLoading}
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              size={isMobile ? "small" : "middle"}
              scroll={isMobile ? { x: 820 } : undefined}
            />
          )}
        </AsyncBoundary>
      </Card>
    </Space>
  );
}
