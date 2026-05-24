import { Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { PositionOrderMatchRead } from "@/api/types";
import { fmtPrice, fmtQty } from "@/utils/format";
import { PnlText } from "./PnlText";
import RelativeTime from "./RelativeTime";

const { Text } = Typography;

interface PositionOrderMatchesPanelProps {
  matches: PositionOrderMatchRead[];
  isSpot?: boolean;
  loading?: boolean;
}

export function PositionOrderMatchesPanel({
  matches,
  isSpot = false,
  loading = false,
}: PositionOrderMatchesPanelProps) {
  const closeLabel = isSpot ? "卖出价" : "平仓价";

  const columns: ColumnsType<PositionOrderMatchRead> = [
    {
      title: "配对时间",
      dataIndex: "matched_at",
      width: 120,
      render: (v: string) => (
        <RelativeTime value={v} style={{ fontSize: 12 }} />
      ),
    },
    {
      title: "匹配数量",
      dataIndex: "matched_qty",
      align: "right",
      width: 100,
      render: (v: number) => <span className="posi-numeric">{fmtQty(v)}</span>,
    },
    {
      title: closeLabel,
      dataIndex: "close_price",
      align: "right",
      width: 110,
      render: (v: number) => (
        <span className="posi-numeric">{fmtPrice(v)}</span>
      ),
    },
    {
      title: "已实现盈亏",
      dataIndex: "realized_pnl",
      align: "right",
      width: 120,
      render: (v: number) => <PnlText value={v} />,
    },
    {
      title: "执行ID",
      dataIndex: "close_order_id",
      width: 80,
      render: (v: number) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          #{v}
        </Text>
      ),
    },
  ];

  if (!loading && matches.length === 0) {
    return (
      <Text type="secondary" style={{ fontSize: 12 }}>
        暂无配对记录
      </Text>
    );
  }

  return (
    <Table
      rowKey="id"
      columns={columns}
      dataSource={matches}
      loading={loading}
      pagination={false}
      size="small"
      scroll={{ x: 560 }}
      locale={{ emptyText: "暂无配对记录" }}
    />
  );
}
