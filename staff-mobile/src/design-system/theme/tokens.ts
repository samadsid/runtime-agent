export const palette = {
  burgundy900: "#5F1518", burgundy800: "#741A1E", burgundy700: "#8F2025",
  burgundy600: "#A6292E", burgundy100: "#F8E5E4", burgundy50: "#FDF3F2",
  cream50: "#FFF9F5", warmWhite: "#FFFCFA", white: "#FFFFFF",
  charcoal950: "#1E1917", charcoal800: "#342D2A", charcoal600: "#6E625D",
  charcoal400: "#9A8E88", stone300: "#D8CEC9", stone200: "#E7DFDA",
  stone100: "#F1EBE7", green700: "#237A4B", green100: "#DCF3E6",
  amber700: "#A65E00", amber100: "#FFF0CF", blue700: "#245EA8",
  blue100: "#E1EEFF", crimson700: "#C3313B", crimson100: "#FBE2E4",
  dark950: "#171311", dark900: "#201B19", dark800: "#2B2421", dark700: "#3A302C",
  cream100: "#F8EEE8", cream300: "#CFC1B9", green300: "#78D5A4",
  amber300: "#F2B85D", blue300: "#8EBBFA", crimson300: "#F38A91",
} as const;

export const spacing = { 0: 0, 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64 } as const;
export const radii = { small: 8, medium: 12, large: 18, xlarge: 24, pill: 999 } as const;
export const breakpoints = { medium: 600, expanded: 900, maxContent: 1440, railWidth: 216 } as const;
export type LayoutTier = "compact" | "medium" | "expanded";

export const typography = {
  display: { compact: 30, expanded: 36, compactLine: 38, expandedLine: 44 },
  titleLarge: { compact: 24, expanded: 28, compactLine: 32, expandedLine: 36 },
  titleMedium: { compact: 20, expanded: 22, compactLine: 28, expandedLine: 30 },
  titleSmall: { compact: 17, expanded: 18, compactLine: 24, expandedLine: 26 },
  bodyLarge: { compact: 16, expanded: 17, compactLine: 24, expandedLine: 26 },
  bodyMedium: { compact: 14, expanded: 15, compactLine: 21, expandedLine: 22 },
  labelLarge: { compact: 14, expanded: 15, compactLine: 20, expandedLine: 21 },
  labelSmall: { compact: 12, expanded: 12, compactLine: 17, expandedLine: 17 },
} as const;
export type TypographyVariant = keyof typeof typography;

export const shadows = {
  none: { elevation: 0 },
  low: { elevation: 2, shadowColor: "#1E1917", shadowOpacity: 0.08, shadowRadius: 4, shadowOffset: { width: 0, height: 2 } },
  medium: { elevation: 5, shadowColor: "#1E1917", shadowOpacity: 0.12, shadowRadius: 10, shadowOffset: { width: 0, height: 4 } },
} as const;

export const motion = { quick: 150, standard: 220 } as const;
