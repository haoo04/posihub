import { useState } from "react";
import {
  Alert,
  Button,
  DatePicker,
  Modal,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  useHistoryImportCommit,
  useHistoryImportPreview,
} from "@/api/hooks";
import type {
  Account,
  ClosedPositionSummaryRead,
  HistoryImportPreviewResponse,
  ImportDedupStatus,
  OrderPreviewRead,
} from "@/api/types";
import { fmtDateTime, fmtPrice, fmtQty, fmtSigned } from "@/utils/format";

const { RangePicker } = DatePicker;
const { Text } = Typography;

const DEDUP_LABEL: Record<ImportDedupStatus, { color: string; label: string }> = {
  new: { color: "green", label: "新增" },
  skip_exists: { color: "default", label: "已存在/跳过" },
  conflict: { color: "red", label: "冲突" },
  orphan_close: { color: "orange", label: "孤儿平仓" },
};

interface Props {
  open: boolean;
  account: Account | null;
  onClose: () => void;
}

export function HistoryImportModal({ open, account, onClose }: Props) {
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [preview, setPreview] = useState<HistoryImportPreviewResponse | null>(
    null
  );
  const previewMutation = useHistoryImportPreview();
  const commitMutation = useHistoryImportCommit();

  const reset = () => {
    setRange(null);
    setPreview(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const onPreview = async () => {
    if (!account || !range) {
      message.warning("请选择时间范围");
      return;
    }
    try {
      const result = await previewMutation.mutateAsync({
        accountId: account.id,
        payload: {
          since: range[0].toISOString(),
          until: range[1].toISOString(),
        },
      });
      setPreview(result);
      if (result.orders.length === 0) {
        message.info("该时间范围内没有可导入的订单");
      }
    } catch (e) {
      message.error((e as Error).message ?? "拉取预览失败");
    }
  };

  const onCommit = () => {
    if (!account || !preview) return;
    Modal.confirm({
      title: "确认写入数据库？",
      content: `将写入 ${preview.summary.new_opens} 笔开仓、${preview.summary.new_closes} 笔平仓。已存在/冲突/孤儿记录将被跳过。`,
      okText: "确认写入",
      cancelText: "取消",
      onOk: async () => {
        try {
          const result = await commitMutation.mutateAsync({
            accountId: account.id,
            previewId: preview.preview_id,
          });
          message.success(
            `写入完成：新增开仓 ${result.created_opens}、平仓 ${result.created_closes}，跳过 ${result.skipped}`
          );
          handleClose();
        } catch (e) {
          message.error((e as Error).message ?? "写入失败");
        }
      },
    });
  };

  const orderColumns: ColumnsType<OrderPreviewRead> = [
    {
      title: "时间",
      dataIndex: "created_at",
      render: (v: string) => fmtDateTime(v),
    },
    {
      title: "交易对",
      dataIndex: "canonical_symbol",
      render: (v: string | null, row) => v ?? <Text type="warning">{row.raw_symbol}（未映射）</Text>,
    },
    {
      title: "方向",
      dataIndex: "side",
      render: (v: string) => (
        <Tag color={v === "long" ? "green" : "red"}>{v === "long" ? "多" : "空"}</Tag>
      ),
    },
    {
      title: "动作",
      dataIndex: "action",
      render: (v: string) => (v === "open" ? "开仓" : "平仓"),
    },
    { title: "数量", dataIndex: "qty", render: (v: number) => fmtQty(v) },
    { title: "价格", dataIndex: "price", render: (v: number) => fmtPrice(v) },
    {
      title: "已实现盈亏",
      dataIndex: "realized_pnl",
      render: (v: number | null) => (v == null ? "—" : fmtSigned(v)),
    },
    {
      title: "状态",
      dataIndex: "dedup_status",
      render: (v: ImportDedupStatus, row) => {
        const meta = DEDUP_LABEL[v];
        const matchInfo =
          row.action === "close" && row.matches.length > 0
            ? `（配对 ${row.matches.length} 笔开仓）`
            : "";
        return (
          <Space direction="vertical" size={0}>
            <Tag color={meta.color}>{meta.label}</Tag>
            {row.note ? <Text type="secondary">{row.note}</Text> : null}
            {matchInfo ? <Text type="secondary">{matchInfo}</Text> : null}
          </Space>
        );
      },
    },
  ];

  const closedColumns: ColumnsType<ClosedPositionSummaryRead> = [
    {
      title: "交易对",
      dataIndex: "canonical_symbol",
      render: (v: string | null, row) => v ?? row.raw_symbol,
    },
    {
      title: "方向",
      dataIndex: "side",
      render: (v: string) => (v === "long" ? "多" : "空"),
    },
    { title: "平仓量", dataIndex: "close_qty", render: (v: number) => fmtQty(v) },
    { title: "开仓均价", dataIndex: "entry_price", render: (v: number) => fmtPrice(v) },
    { title: "平仓均价", dataIndex: "close_price", render: (v: number) => fmtPrice(v) },
    {
      title: "交易所已实现盈亏",
      dataIndex: "realized_pnl",
      render: (v: number) => fmtSigned(v),
    },
    {
      title: "平仓时间",
      dataIndex: "close_time",
      render: (v: string | null) => fmtDateTime(v),
    },
  ];

  const summary = preview?.summary;
  const hasBlockers = (preview?.blockers.length ?? 0) > 0;

  return (
    <Modal
      open={open}
      title={account ? `历史回填 · ${account.account_name}` : "历史回填"}
      width={920}
      onCancel={handleClose}
      footer={[
        <Button key="cancel" onClick={handleClose}>
          关闭
        </Button>,
        <Button
          key="commit"
          type="primary"
          disabled={!preview || hasBlockers || (summary?.new_opens ?? 0) + (summary?.new_closes ?? 0) === 0}
          loading={commitMutation.isPending}
          onClick={onCommit}
        >
          确认写入数据库
        </Button>,
      ]}
      destroyOnClose
    >
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Alert
          type="info"
          message="先选择时间范围拉取预览，确认无误后再写入。交易所历史查询单次最长 90 天，超出会自动分片。"
        />
        <Space wrap>
          <RangePicker
            showTime
            value={range}
            onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)}
            disabledDate={(d) => !!d && d.isAfter(dayjs().endOf("day"))}
          />
          <Button
            type="primary"
            loading={previewMutation.isPending}
            onClick={onPreview}
          >
            拉取预览
          </Button>
        </Space>

        {preview ? (
          <>
            <Space size="large" wrap>
              <Statistic title="拉取总数" value={summary?.total_fetched ?? 0} />
              <Statistic title="新增开仓" value={summary?.new_opens ?? 0} />
              <Statistic title="新增平仓" value={summary?.new_closes ?? 0} />
              <Statistic title="跳过" value={summary?.skipped ?? 0} />
              <Statistic
                title="冲突"
                value={summary?.conflicts ?? 0}
                valueStyle={{ color: (summary?.conflicts ?? 0) > 0 ? "#cf1322" : undefined }}
              />
              <Statistic
                title="孤儿平仓"
                value={summary?.orphans ?? 0}
                valueStyle={{ color: (summary?.orphans ?? 0) > 0 ? "#d46b08" : undefined }}
              />
              <Statistic
                title="盈亏校验告警"
                value={summary?.pnl_validation_warnings ?? 0}
              />
            </Space>

            {hasBlockers ? (
              <Alert
                type="error"
                message="存在阻断项，需处理后才能写入"
                description={
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {preview.blockers.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                }
              />
            ) : null}

            <Tabs
              items={[
                {
                  key: "orders",
                  label: `订单明细 (${preview.orders.length})`,
                  children: (
                    <Table
                      rowKey={(r) => `${r.source_order_id}-${r.action}`}
                      size="small"
                      columns={orderColumns}
                      dataSource={preview.orders}
                      pagination={{ pageSize: 10, size: "small" }}
                      scroll={{ x: 720 }}
                    />
                  ),
                },
                {
                  key: "closed",
                  label: `历史仓位对照 (${preview.closed_positions.length})`,
                  children: (
                    <Table
                      rowKey={(r) => `${r.raw_symbol}-${r.side}-${r.close_time ?? ""}`}
                      size="small"
                      columns={closedColumns}
                      dataSource={preview.closed_positions}
                      pagination={{ pageSize: 10, size: "small" }}
                      scroll={{ x: 720 }}
                    />
                  ),
                },
              ]}
            />
          </>
        ) : null}
      </Space>
    </Modal>
  );
}
