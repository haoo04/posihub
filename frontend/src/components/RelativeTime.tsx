import { Tooltip, Typography } from "antd";
import { fmtDateTime, fmtRelative } from "../utils/format";

const { Text } = Typography;

interface RelativeTimeProps {
  value: string | null | undefined;
  type?: "secondary" | "success" | "warning" | "danger";
  style?: React.CSSProperties;
}

export default function RelativeTime({
  value,
  type = "secondary",
  style
}: RelativeTimeProps) {
  if (!value) {
    return (
      <Text type={type} style={style}>
        —
      </Text>
    );
  }

  return (
    <Tooltip title={fmtDateTime(value)} placement="top">
      <Text type={type} style={{ ...style, cursor: "help" }}>
        {fmtRelative(value)}
      </Text>
    </Tooltip>
  );
}
