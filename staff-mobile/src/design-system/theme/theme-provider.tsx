import { createContext, type PropsWithChildren, useContext, useMemo } from "react";
import { useColorScheme } from "react-native";

import { palette, radii, shadows, spacing, typography } from "./tokens";

const lightColors = {
  background: palette.cream50, surface: palette.white, surfaceRaised: palette.warmWhite,
  surfaceMuted: palette.stone100, overlay: "rgba(30, 25, 23, 0.48)",
  textPrimary: palette.charcoal950, textSecondary: palette.charcoal600,
  textDisabled: palette.charcoal400, textOnBrand: palette.white,
  border: palette.stone200, borderStrong: palette.stone300, focus: palette.burgundy700,
  brand: palette.burgundy700, brandPressed: palette.burgundy900, brandSubtle: palette.burgundy50,
  success: palette.green700, successSubtle: palette.green100,
  warning: palette.amber700, warningSubtle: palette.amber100,
  info: palette.blue700, infoSubtle: palette.blue100,
  danger: palette.crimson700, dangerSubtle: palette.crimson100,
} as const;

const darkColors: { [K in keyof typeof lightColors]: string } = {
  background: palette.dark950, surface: palette.dark900, surfaceRaised: palette.dark800,
  surfaceMuted: palette.dark700, overlay: "rgba(0, 0, 0, 0.66)",
  textPrimary: palette.cream100, textSecondary: palette.cream300,
  textDisabled: palette.charcoal400, textOnBrand: palette.white,
  border: palette.dark700, borderStrong: "#594A44", focus: palette.crimson300,
  brand: palette.crimson300, brandPressed: "#F5A4A9", brandSubtle: "#3B2021",
  success: palette.green300, successSubtle: "#193528", warning: palette.amber300,
  warningSubtle: "#3A2B17", info: palette.blue300, infoSubtle: "#1A2C43",
  danger: palette.crimson300, dangerSubtle: "#421F22",
};

export type SemanticColors = { [K in keyof typeof lightColors]: string };
export type AppTheme = {
  mode: "light" | "dark";
  colors: SemanticColors;
  spacing: typeof spacing;
  radii: typeof radii;
  typography: typeof typography;
  shadows: typeof shadows;
};

const ThemeContext = createContext<AppTheme | null>(null);

export function ThemeProvider({ children }: PropsWithChildren) {
  const scheme = useColorScheme();
  const theme = useMemo<AppTheme>(() => ({
    mode: scheme === "dark" ? "dark" : "light",
    colors: scheme === "dark" ? darkColors : lightColors,
    spacing, radii, typography,
    shadows,
  }), [scheme]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): AppTheme {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}

export { darkColors, lightColors };
