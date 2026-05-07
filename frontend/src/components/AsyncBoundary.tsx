import type { ReactNode } from "react";
import { Alert, Empty, Skeleton } from "antd";

interface Props {
  loading?: boolean;
  error?: unknown;
  empty?: boolean;
  emptyText?: ReactNode;
  skeletonRows?: number;
  children: ReactNode;
}

export function AsyncBoundary({
  loading,
  error,
  empty,
  emptyText = "暂无数据",
  skeletonRows = 4,
  children,
}: Props) {
  if (loading) {
    return (
      <Skeleton active paragraph={{ rows: skeletonRows }} title={false} />
    );
  }
  if (error) {
    const message =
      (error as Error)?.message ?? "请求失败，请稍后重试";
    return <Alert type="error" message={message} showIcon />;
  }
  if (empty) {
    return <Empty description={emptyText} style={{ padding: "32px 0" }} />;
  }
  return <>{children}</>;
}
