import { useWindowDimensions } from "react-native";

import { breakpoints, type LayoutTier } from "../theme/tokens";

export function getLayoutTier(width: number): LayoutTier {
  if (width >= breakpoints.expanded) return "expanded";
  if (width >= breakpoints.medium) return "medium";
  return "compact";
}

export function getGridColumns(contentWidth: number, minimumItemWidth: number, gap: number, maximum = 3): number {
  return Math.max(1, Math.min(maximum, Math.floor((contentWidth + gap) / (minimumItemWidth + gap))));
}

export function useResponsiveLayout() {
  const { width, height, fontScale } = useWindowDimensions();
  const tier = getLayoutTier(width);
  const horizontalPadding = tier === "compact" ? 16 : tier === "medium" ? 24 : 32;
  const navigationWidth = tier === "compact" ? 0 : breakpoints.railWidth;
  const contentWidth = Math.min(width - navigationWidth - horizontalPadding * 2, breakpoints.maxContent);
  return { width, height, fontScale, tier, horizontalPadding, navigationWidth, contentWidth, expanded: tier === "expanded", compact: tier === "compact" } as const;
}
