import { useColorScheme } from "react-native";

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radii = { sm: 8, md: 12, lg: 18 } as const;

const light = {
  background: "#F5F7FA", surface: "#FFFFFF", text: "#17202A", muted: "#59636E",
  border: "#D6DCE2", primary: "#175CD3", primaryText: "#FFFFFF", danger: "#B42318",
  dangerSurface: "#FEE4E2", success: "#067647", warning: "#B54708", infoSurface: "#EAF2FF",
};
const dark = {
  background: "#101418", surface: "#1B2229", text: "#F4F6F8", muted: "#B4BEC8",
  border: "#3C4650", primary: "#84ADFF", primaryText: "#071426", danger: "#FDA29B",
  dangerSurface: "#55160C", success: "#75E0A7", warning: "#FEC84B", infoSurface: "#172A46",
};

export function useTheme() { return useColorScheme() === "dark" ? dark : light; }
