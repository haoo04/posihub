import type { ReactNode } from "react";
import { Alert, Empty, Skeleton } from "antd";
import { useLocale } from "@/i18n/LocaleContext";

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
  emptyText,
  skeletonRows = 4,
  children,
}: Props) {
  const { t } = useLocale();

  if (loading) {
    return (
      <Skeleton active paragraph={{ rows: skeletonRows }} title={false} />
    );
  }
  if (error) {
    const message =
      (error as Error)?.message ?? t("common.requestFailed");
    return <Alert type="error" message={message} showIcon />;
  }
  if (empty) {
    return (
      <Empty
        description={emptyText ?? t("common.noData")}
        style={{ padding: "32px 0" }}
      />
    );
  }
  return <>{children}</>;
}
