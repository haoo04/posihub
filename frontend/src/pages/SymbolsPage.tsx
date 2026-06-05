import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  DeleteOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { PageHeader } from "@/components/PageHeader";
import { AsyncBoundary } from "@/components/AsyncBoundary";
import {
  useDeleteSymbol,
  useSymbols,
  useUpdateSymbol,
} from "@/api/hooks";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { exportCsv } from "@/utils/csv";
import type { InstrumentType, SymbolMapping } from "@/api/types";

const { Text } = Typography;

const INSTRUMENT_COLOR: Record<InstrumentType, string> = {
  spot: "green",
  perp: "blue",
  futures: "purple",
};

export function SymbolsPage() {
  const { isMobile } = useBreakpoint();
  const symbols = useSymbols();
  const updateSymbol = useUpdateSymbol();
  const deleteSymbol = useDeleteSymbol();
  const [keyword, setKeyword] = useState("");
  const [exchange, setExchange] = useState<string | undefined>(undefined);

  const exchangeOptions = useMemo(() => {
    const set = new Set((symbols.data ?? []).map((s) => s.exchange));
    return Array.from(set)
      .sort()
      .map((e) => ({ value: e, label: e }));
  }, [symbols.data]);

  const filtered = useMemo(() => {
    const k = keyword.trim().toUpperCase();
    return (symbols.data ?? [])
      .filter((s) => !exchange || s.exchange === exchange)
      .filter(
        (s) =>
          !k ||
          `${s.raw_symbol} ${s.canonical_symbol} ${s.base_asset} ${s.quote_asset}`
            .toUpperCase()
            .includes(k)
      )
      .sort((a, b) => {
        const ex = a.exchange.localeCompare(b.exchange);
        if (ex !== 0) return ex;
        return a.canonical_symbol.localeCompare(b.canonical_symbol);
      });
  }, [symbols.data, keyword, exchange]);

  const onToggle = async (row: SymbolMapping, value: boolean) => {
    try {
      await updateSymbol.mutateAsync({ id: row.id, patch: { is_active: value } });
    } catch (e) {
      message.error((e as Error).message ?? "更新失败");
    }
  };

  const onDelete = async (id: number) => {
    try {
      await deleteSymbol.mutateAsync(id);
      message.success("已删除映射");
    } catch (e) {
      message.error((e as Error).message ?? "删除失败");
    }
  };

  const onExport = () => {
    exportCsv<SymbolMapping>(
      `symbol-mappings-${new Date().toISOString().slice(0, 10)}.csv`,
      [
        { header: "交易所", value: (r) => r.exchange },
        { header: "原始符号", value: (r) => r.raw_symbol },
        { header: "统一符号", value: (r) => r.canonical_symbol },
        { header: "基础币", value: (r) => r.base_asset },
        { header: "计价币", value: (r) => r.quote_asset },
        { header: "类型", value: (r) => r.instrument_type },
        { header: "合约乘数", value: (r) => r.contract_size },
        { header: "启用", value: (r) => (r.is_active ? "是" : "否") },
      ],
      filtered
    );
  };

  const columns: ColumnsType<SymbolMapping> = [
    {
      title: "交易所",
      dataIndex: "exchange",
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: "原始符号",
      dataIndex: "raw_symbol",
      render: (v: string) => <span className="posi-mono">{v}</span>,
    },
    {
      title: "统一符号",
      dataIndex: "canonical_symbol",
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "基础 / 计价",
      key: "assets",
      render: (_: unknown, row) => (
        <Text type="secondary">
          {row.base_asset} / {row.quote_asset}
        </Text>
      ),
    },
    {
      title: "类型",
      dataIndex: "instrument_type",
      render: (v: InstrumentType) => (
        <Tag color={INSTRUMENT_COLOR[v] ?? "default"}>{v}</Tag>
      ),
    },
    {
      title: "乘数",
      dataIndex: "contract_size",
      align: "right" as const,
      render: (v: number) => <span className="posi-numeric">{v}</span>,
    },
    {
      title: "启用",
      dataIndex: "is_active",
      render: (v: boolean, row) => (
        <Switch
          size="small"
          checked={v}
          loading={
            updateSymbol.isPending && updateSymbol.variables?.id === row.id
          }
          onChange={(checked) => onToggle(row, checked)}
        />
      ),
    },
    {
      title: "操作",
      key: "actions",
      align: "right" as const,
      render: (_: unknown, row) => (
        <Popconfirm
          title="确认删除该映射？"
          okText="删除"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          onConfirm={() => onDelete(row.id)}
        >
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <PageHeader
        title="Symbol 映射"
        description="统一各交易所 raw_symbol → canonical_symbol，消除命名差异"
        extra={
          <>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索符号 / 币种"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              style={{ width: isMobile ? "100%" : 220, maxWidth: "100%" }}
            />
            <Select
              allowClear
              placeholder="交易所"
              value={exchange}
              onChange={(v?: string) => setExchange(v)}
              options={exchangeOptions}
              style={{ width: isMobile ? "100%" : 160 }}
            />
            <Button
              icon={<ReloadOutlined />}
              loading={symbols.isFetching}
              onClick={() => symbols.refetch()}
            >
              刷新
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={onExport}
              disabled={!filtered.length}
            >
              导出 CSV
            </Button>
          </>
        }
      />

      <Card bodyStyle={{ padding: 0 }} style={{ borderRadius: 12 }}>
        <AsyncBoundary
          loading={symbols.isLoading}
          error={symbols.error}
          empty={!filtered.length}
          emptyText="暂无映射，可通过种子脚本或接口写入"
        >
          <Table<SymbolMapping>
            rowKey="id"
            columns={columns}
            dataSource={filtered}
            loading={symbols.isFetching && !symbols.isLoading}
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            size={isMobile ? "small" : "middle"}
            scroll={isMobile ? { x: 760 } : undefined}
          />
        </AsyncBoundary>
      </Card>
    </Space>
  );
}
