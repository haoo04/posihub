import { Grid } from "antd";

/** Ant Design 断点：https://ant.design/components/grid#col */
export function useBreakpoint() {
  const screens = Grid.useBreakpoint();

  const mdUp = !!screens.md;
  const lgUp = !!screens.lg;

  /** 手机 / 窄屏：&lt; 768px */
  const isMobile = !mdUp;

  return { screens, mdUp, lgUp, isMobile };
}
