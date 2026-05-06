import type { ReactNode } from "react";
import { Space, Typography } from "antd";

const { Title, Text } = Typography;

interface Props {
  title: ReactNode;
  description?: ReactNode;
  extra?: ReactNode;
}

export function PageHeader({ title, description, extra }: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 16,
        marginBottom: 20,
      }}
    >
      <div>
        <Title
          level={4}
          style={{
            margin: 0,
            color: "var(--posi-text)",
            fontWeight: 600,
            letterSpacing: "-0.01em",
          }}
        >
          {title}
        </Title>
        {description && (
          <Text type="secondary" style={{ fontSize: 13 }}>
            {description}
          </Text>
        )}
      </div>
      {extra && <Space size={8}>{extra}</Space>}
    </div>
  );
}
