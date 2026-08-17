import Ionicons from "@expo/vector-icons/Ionicons";
import type { ComponentProps, PropsWithChildren, ReactNode } from "react";
import {
  ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput,
  type TextInputProps, View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { useResponsiveLayout } from "./responsive/use-responsive-layout";
import { useTheme } from "./theme/theme-provider";
import { radii, spacing, typography, type TypographyVariant } from "./theme/tokens";

export { getGridColumns, getLayoutTier, useResponsiveLayout } from "./responsive/use-responsive-layout";
export { ThemeProvider, useTheme } from "./theme/theme-provider";
export { breakpoints, motion, radii, shadows, spacing, typography } from "./theme/tokens";
export type { AppTheme, SemanticColors } from "./theme/theme-provider";
export type { LayoutTier, TypographyVariant } from "./theme/tokens";

type TextColor = "primary" | "secondary" | "brand" | "success" | "warning" | "info" | "danger" | "onBrand";
type TextWeight = "regular" | "medium" | "semibold" | "bold";

export function AppText({ variant = "bodyMedium", color = "primary", weight = "regular", align, children, selectable, numberOfLines, style, accessibilityRole }: PropsWithChildren<{
  variant?: TypographyVariant; color?: TextColor; weight?: TextWeight; align?: "left" | "center" | "right";
  selectable?: boolean; numberOfLines?: number; style?: ComponentProps<typeof Text>["style"];
  accessibilityRole?: ComponentProps<typeof Text>["accessibilityRole"];
}>) {
  const theme = useTheme();
  const { expanded } = useResponsiveLayout();
  const token = typography[variant];
  const textColor = { primary: theme.colors.textPrimary, secondary: theme.colors.textSecondary,
    brand: theme.colors.brand, success: theme.colors.success, warning: theme.colors.warning,
    info: theme.colors.info, danger: theme.colors.danger, onBrand: theme.colors.textOnBrand }[color];
  const fontWeight = { regular: "400", medium: "500", semibold: "600", bold: "700" }[weight] as "400" | "500" | "600" | "700";
  return <Text selectable={selectable} numberOfLines={numberOfLines} accessibilityRole={accessibilityRole} style={[{ color: textColor, fontSize: expanded ? token.expanded : token.compact, lineHeight: expanded ? token.expandedLine : token.compactLine, fontWeight, textAlign: align }, style]}>{children}</Text>;
}

export function Screen({ children }: PropsWithChildren) {
  const theme = useTheme();
  return <View style={[styles.screen, { backgroundColor: theme.colors.background }]}>{children}</View>;
}

export function ResponsiveContainer({ children, scroll = false, keyboardShouldPersistTaps = "handled", contentStyle }: PropsWithChildren<{
  scroll?: boolean; keyboardShouldPersistTaps?: "always" | "never" | "handled"; contentStyle?: ComponentProps<typeof View>["style"];
}>) {
  const { horizontalPadding } = useResponsiveLayout();
  const theme = useTheme();
  const body = <View style={[styles.containerContent, { paddingHorizontal: horizontalPadding }, contentStyle]}>{children}</View>;
  return <SafeAreaView edges={["top", "left", "right"]} style={[styles.screen, { backgroundColor: theme.colors.background }]}>{scroll
    ? <ScrollView contentContainerStyle={styles.scrollGrow} keyboardShouldPersistTaps={keyboardShouldPersistTaps}>{body}</ScrollView>
    : body}</SafeAreaView>;
}

export function Stack({ children, gap = 4, style }: PropsWithChildren<{ gap?: keyof typeof spacing; style?: ComponentProps<typeof View>["style"] }>) {
  return <View style={[{ gap: spacing[gap] }, style]}>{children}</View>;
}

export function Inline({ children, gap = 2, wrap = false, between = false, style }: PropsWithChildren<{ gap?: keyof typeof spacing; wrap?: boolean; between?: boolean; style?: ComponentProps<typeof View>["style"] }>) {
  return <View style={[styles.inline, { gap: spacing[gap], flexWrap: wrap ? "wrap" : "nowrap", justifyContent: between ? "space-between" : "flex-start" }, style]}>{children}</View>;
}

export function Divider() { const theme = useTheme(); return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: theme.colors.border }} />; }

type IconName = ComponentProps<typeof Ionicons>["name"];
export function AppIcon({ name, size = 20, color = "primary", accessibilityLabel }: { name: IconName; size?: number; color?: TextColor; accessibilityLabel?: string }) {
  const theme = useTheme();
  const iconColor = { primary: theme.colors.textPrimary, secondary: theme.colors.textSecondary,
    brand: theme.colors.brand, success: theme.colors.success, warning: theme.colors.warning,
    info: theme.colors.info, danger: theme.colors.danger, onBrand: theme.colors.textOnBrand }[color];
  return <Ionicons name={name} size={size} color={iconColor} accessibilityLabel={accessibilityLabel} />;
}

export type ButtonVariant = "primary" | "secondary" | "tertiary" | "danger";
export function Button({ label, onPress, disabled = false, loading = false, variant = "primary", icon, accessibilityHint, testID }: {
  label: string; onPress(): void; disabled?: boolean; loading?: boolean; variant?: ButtonVariant;
  icon?: IconName; accessibilityHint?: string; testID?: string;
}) {
  const theme = useTheme(); const unavailable = disabled || loading;
  const background = variant === "primary" ? theme.colors.brand : variant === "danger" ? theme.colors.danger : variant === "secondary" ? theme.colors.surface : "transparent";
  const foreground: TextColor = variant === "primary" || variant === "danger" ? "onBrand" : variant === "tertiary" ? "brand" : "primary";
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityHint={accessibilityHint}
    accessibilityState={{ disabled: unavailable, busy: loading }} disabled={unavailable} onPress={onPress} testID={testID}
    style={({ pressed }) => [styles.button, { backgroundColor: background, borderColor: variant === "danger" ? theme.colors.danger : variant === "tertiary" ? "transparent" : theme.colors.borderStrong, opacity: unavailable ? 0.56 : 1, transform: [{ scale: pressed ? 0.99 : 1 }] }]}>
    {loading ? <ActivityIndicator color={variant === "primary" || variant === "danger" ? theme.colors.textOnBrand : theme.colors.brand} /> : <Inline gap={2}>{icon ? <AppIcon name={icon} color={foreground} /> : null}<AppText variant="labelLarge" color={foreground} weight="bold">{label}</AppText></Inline>}
  </Pressable>;
}

export function IconButton({ name, label, onPress, disabled }: { name: IconName; label: string; onPress(): void; disabled?: boolean }) {
  const theme = useTheme();
  return <Pressable accessibilityRole="button" accessibilityLabel={label} disabled={disabled} accessibilityState={{ disabled }} onPress={onPress}
    style={({ pressed }) => [styles.iconButton, { backgroundColor: pressed ? theme.colors.brandSubtle : "transparent", opacity: disabled ? 0.5 : 1 }]}><AppIcon name={name} color="brand" /></Pressable>;
}

export function TextField({ label, error, help, required, trailing, ...props }: TextInputProps & { label: string; error?: string; help?: string; required?: boolean; trailing?: ReactNode }) {
  const theme = useTheme();
  const message = error ?? help;
  return <View style={styles.field}><Inline gap={1}><AppText variant="labelLarge" weight="semibold">{label}</AppText>{required ? <AppText variant="labelLarge" color="danger">*</AppText> : null}</Inline>
    <View style={[styles.inputFrame, { borderColor: error ? theme.colors.danger : theme.colors.borderStrong, backgroundColor: props.editable === false ? theme.colors.surfaceMuted : theme.colors.surface }]}>
      <TextInput accessibilityLabel={label} accessibilityState={{ disabled: props.editable === false }} placeholderTextColor={theme.colors.textDisabled} {...props} style={[styles.input, { color: theme.colors.textPrimary }, props.style]} />{trailing}
    </View>{message ? <AppText variant="labelSmall" color={error ? "danger" : "secondary"}>{message}</AppText> : null}</View>;
}
export const SearchField = (props: Omit<ComponentProps<typeof TextField>, "trailing">) => <TextField {...props} returnKeyType="search" trailing={<View style={styles.trailingIcon}><AppIcon name="search-outline" color="secondary" /></View>} />;
export const Field = TextField;

export function Card({ children, variant = "default", onPress, accessibilityLabel }: PropsWithChildren<{ variant?: "default" | "outlined" | "interactive" | "tonal"; onPress?: () => void; accessibilityLabel?: string }>) {
  const theme = useTheme();
  const cardStyle = [styles.card, { backgroundColor: variant === "tonal" ? theme.colors.surfaceMuted : theme.colors.surface, borderColor: theme.colors.border, ...(variant === "default" ? theme.shadows.low : {}) }];
  return onPress ? <Pressable accessibilityRole="button" accessibilityLabel={accessibilityLabel} onPress={onPress} style={({ pressed }) => [cardStyle, { borderColor: pressed ? theme.colors.focus : theme.colors.border }]}>{children}</Pressable> : <View style={cardStyle}>{children}</View>;
}

type Tone = "brand" | "success" | "warning" | "info" | "danger" | "neutral";
export function StatusBadge({ label, tone = "neutral", icon }: { label: string; tone?: Tone; icon?: IconName }) {
  const theme = useTheme();
  const foreground = tone === "neutral" ? theme.colors.textSecondary : theme.colors[tone];
  const background = tone === "neutral" ? theme.colors.surfaceMuted : theme.colors[`${tone}Subtle` as "brandSubtle"];
  return <View accessibilityLabel={`Status: ${label}`} style={[styles.badge, { backgroundColor: background, borderColor: foreground }]}><Inline gap={1}>{icon ? <Ionicons name={icon} size={14} color={foreground} /> : null}<AppText variant="labelSmall" weight="bold" style={{ color: foreground }}>{label}</AppText></Inline></View>;
}

export function FilterChip({ label, selected, onPress }: { label: string; selected?: boolean; onPress(): void }) {
  const theme = useTheme();
  return <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={onPress} style={({ pressed }) => [styles.chip, { backgroundColor: selected ? theme.colors.brandSubtle : theme.colors.surface, borderColor: selected ? theme.colors.brand : theme.colors.borderStrong, opacity: pressed ? 0.8 : 1 }]}><AppText variant="labelLarge" color={selected ? "brand" : "primary"} weight={selected ? "bold" : "medium"}>{label}</AppText></Pressable>;
}

export function MetricCard({ label, value, tone = "brand", icon, onPress }: { label: string; value: string | number; tone?: Exclude<Tone, "neutral" | "danger">; icon: IconName; onPress?: () => void }) {
  return <Card variant="tonal" onPress={onPress} accessibilityLabel={`${label}: ${value}`}><Inline between><AppIcon name={icon} color={tone} /><AppText variant="display" weight="bold">{value}</AppText></Inline><AppText variant="bodyMedium" color="secondary" weight="semibold">{label}</AppText></Card>;
}

export function SectionHeader({ title, action }: { title: string; action?: ReactNode }) { return <Inline between><AppText variant="titleMedium" weight="bold">{title}</AppText>{action}</Inline>; }
export function KeyValueRow({ label, value, primary = false }: { label: string; value: string; primary?: boolean }) { return <Inline between style={styles.keyValue}><AppText color="secondary">{label}</AppText><AppText variant={primary ? "titleSmall" : "bodyMedium"} weight={primary ? "bold" : "semibold"} style={styles.keyValueValue}>{value}</AppText></Inline>; }

export function Banner({ message, tone = "warning", action }: { message: string; tone?: "warning" | "info" | "danger" | "success"; action?: ReactNode }) {
  const theme = useTheme();
  return <View accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.banner, { backgroundColor: theme.colors[`${tone}Subtle`], borderColor: theme.colors[tone] }]}><AppIcon name={tone === "warning" ? "warning-outline" : tone === "danger" ? "alert-circle-outline" : tone === "success" ? "checkmark-circle-outline" : "information-circle-outline"} color={tone} /><AppText variant="bodyMedium" style={styles.bannerText}>{message}</AppText>{action}</View>;
}

export function StateMessage({ title, message, action, kind = "empty" }: { title: string; message?: string; action?: ReactNode; kind?: "empty" | "error" }) {
  return <View style={styles.state} accessibilityLiveRegion="polite"><AppIcon name={kind === "error" ? "alert-circle-outline" : "file-tray-outline"} size={32} color={kind === "error" ? "danger" : "secondary"} /><AppText variant="titleMedium" weight="bold" align="center">{title}</AppText>{message ? <AppText variant="bodyMedium" color="secondary" align="center">{message}</AppText> : null}{action}</View>;
}
export const EmptyState = StateMessage;
export function ErrorState(props: Omit<ComponentProps<typeof StateMessage>, "kind"> & { requestId?: string }) { return <StateMessage {...props} kind="error" message={[props.message, props.requestId ? `Request ${props.requestId}` : null].filter(Boolean).join(" ")} />; }
export function Loading({ label = "Loading" }: { label?: string }) { const theme = useTheme(); return <View style={styles.state} accessibilityLabel={label} accessibilityLiveRegion="polite"><ActivityIndicator color={theme.colors.brand} /><AppText color="secondary">{label}</AppText></View>; }

export function LoadingSkeleton({ rows = 3 }: { rows?: number }) { const theme = useTheme(); return <View accessibilityLabel="Loading" style={styles.skeletonList}>{Array.from({ length: rows }, (_, index) => <View key={index} style={[styles.skeleton, { backgroundColor: theme.colors.surfaceMuted }]} />)}</View>; }

export function Confirmation({ visible, title, message, confirmLabel, danger, busy, children, onConfirm, onCancel }: PropsWithChildren<{ visible: boolean; title: string; message: string; confirmLabel: string; danger?: boolean; busy?: boolean; onConfirm(): void; onCancel(): void }>) {
  const theme = useTheme(); const { compact } = useResponsiveLayout(); const insets = useSafeAreaInsets();
  return <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}><View style={[styles.overlay, { backgroundColor: theme.colors.overlay, justifyContent: compact ? "flex-end" : "center" }]}><View accessibilityViewIsModal style={[styles.confirmation, compact ? styles.sheet : styles.dialog, { backgroundColor: theme.colors.surface, paddingBottom: spacing[6] + insets.bottom }]}><AppText variant="titleMedium" weight="bold">{title}</AppText><AppText color="secondary">{message}</AppText>{children}<Button variant={danger ? "danger" : "primary"} label={confirmLabel} loading={busy} onPress={onConfirm} /><Button variant="tertiary" label="Back" disabled={busy} onPress={onCancel} /></View></View></Modal>;
}

export function ResponsiveGrid({ children, minimumItemWidth = 260 }: PropsWithChildren<{ minimumItemWidth?: number }>) {
  const { contentWidth } = useResponsiveLayout();
  const columns = Math.max(1, Math.min(3, Math.floor((contentWidth + spacing[3]) / (minimumItemWidth + spacing[3]))));
  return <View style={styles.grid}>{Array.isArray(children) ? children.map((child, index) => <View key={index} style={{ width: `${100 / columns}%`, padding: spacing[1] }}>{child}</View>) : <View style={{ flex: 1 }}>{children}</View>}</View>;
}

export const dsStyles = StyleSheet.create({ page: { padding: spacing[4], gap: spacing[4] }, row: { flexDirection: "row", alignItems: "center", gap: spacing[2] }, title: { fontSize: 24, lineHeight: 32, fontWeight: "700" }, heading: { fontSize: 20, lineHeight: 28, fontWeight: "700" }, body: { fontSize: 16, lineHeight: 24 } });

const styles = StyleSheet.create({
  screen: { flex: 1 }, scrollGrow: { flexGrow: 1 }, containerContent: { flex: 1, width: "100%", maxWidth: 1440, alignSelf: "center", paddingVertical: spacing[4] },
  inline: { flexDirection: "row", alignItems: "center" }, button: { minHeight: 48, borderRadius: radii.small, borderWidth: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing[4], paddingVertical: spacing[2] },
  iconButton: { width: 48, height: 48, borderRadius: radii.pill, alignItems: "center", justifyContent: "center" }, field: { gap: spacing[1] }, inputFrame: { minHeight: 50, flexDirection: "row", alignItems: "center", borderWidth: 1, borderRadius: radii.small }, input: { flex: 1, minHeight: 48, paddingHorizontal: spacing[4], fontSize: 16 }, trailingIcon: { paddingRight: spacing[3] },
  card: { padding: spacing[4], borderRadius: radii.medium, borderWidth: 1, gap: spacing[2] }, badge: { alignSelf: "flex-start", borderWidth: 1, borderRadius: radii.pill, paddingHorizontal: spacing[2], paddingVertical: spacing[1] }, chip: { minHeight: 44, justifyContent: "center", borderWidth: 1, borderRadius: radii.pill, paddingHorizontal: spacing[3], paddingVertical: spacing[2] },
  keyValue: { alignItems: "flex-start" }, keyValueValue: { flex: 1, textAlign: "right" }, banner: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: spacing[2], borderBottomWidth: 1, paddingHorizontal: spacing[4], paddingVertical: spacing[2] }, bannerText: { flex: 1 }, state: { flexGrow: 1, minHeight: 180, padding: spacing[6], alignItems: "center", justifyContent: "center", gap: spacing[3] },
  skeletonList: { gap: spacing[3], paddingVertical: spacing[3] }, skeleton: { height: 104, borderRadius: radii.medium }, overlay: { flex: 1, alignItems: "center" }, confirmation: { width: "100%", gap: spacing[4], padding: spacing[6] }, sheet: { borderTopLeftRadius: radii.xlarge, borderTopRightRadius: radii.xlarge }, dialog: { maxWidth: 480, borderRadius: radii.large }, grid: { flexDirection: "row", flexWrap: "wrap", margin: -spacing[1] },
});
