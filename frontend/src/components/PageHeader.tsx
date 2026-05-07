import {
  Children,
  Fragment,
  isValidElement,
  type ReactNode,
} from "react";
import { Flex, Grid, Typography } from "antd";

const { Title, Text } = Typography;
const { useBreakpoint } = Grid;

interface Props {
  title: ReactNode;
  description?: ReactNode;
  extra?: ReactNode;
}

/** Flatten `<></>` so toolbar buttons wrap correctly on narrow screens. */
function flattenExtra(nodes: ReactNode): ReactNode[] {
  return Children.toArray(nodes).flatMap((n) => {
    if (isValidElement(n) && n.type === Fragment) {
      return flattenExtra(n.props.children);
    }
    return [n];
  });
}

export function PageHeader({ title, description, extra }: Props) {
  const screens = useBreakpoint();
  const mdUp = !!screens.md;

  return (
    <Flex
      vertical={!mdUp}
      gap={mdUp ? 16 : 12}
      align={mdUp ? "flex-start" : "stretch"}
      justify="space-between"
      style={{ marginBottom: mdUp ? 20 : 16 }}
    >
      <div style={{ flex: mdUp ? "0 1 auto" : undefined, minWidth: 0 }}>
        <Title
          level={4}
          style={{
            margin: 0,
            color: "var(--posi-text)",
            fontWeight: 600,
            letterSpacing: "-0.01em",
            fontSize: mdUp ? 20 : 18,
          }}
        >
          {title}
        </Title>
        {description && (
          <Text type="secondary" style={{ fontSize: mdUp ? 13 : 12 }}>
            {description}
          </Text>
        )}
      </div>
      {extra ? (
        <Flex
          wrap="wrap"
          gap={8}
          justify={mdUp ? "flex-end" : "flex-start"}
          style={{ width: mdUp ? "auto" : "100%" }}
        >
          {flattenExtra(extra)}
        </Flex>
      ) : null}
    </Flex>
  );
}
