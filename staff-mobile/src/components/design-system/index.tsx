import type { PropsWithChildren, ReactNode } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, type TextInputProps, View } from "react-native";

import type { OrderStatus } from "@/api/contracts";
import { radii, spacing, useTheme } from "./theme";

export function Screen({ children }: PropsWithChildren) {
  const theme = useTheme();
  return <View style={[styles.screen, { backgroundColor: theme.background }]}>{children}</View>;
}

export function Card({ children }: PropsWithChildren) {
  const theme = useTheme();
  return <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>{children}</View>;
}

export function Button({ label, onPress, disabled, variant = "primary", testID }: {
  label: string; onPress(): void; disabled?: boolean; variant?: "primary" | "secondary" | "destructive"; testID?: string;
}) {
  const theme = useTheme();
  const background = variant === "destructive" ? theme.danger : variant === "secondary" ? theme.surface : theme.primary;
  const color = variant === "secondary" ? theme.text : theme.primaryText;
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    testID={testID} style={({ pressed }) => [styles.button, { backgroundColor: background, borderColor: theme.border, opacity: disabled ? 0.5 : pressed ? 0.8 : 1 }]}> 
    <Text style={[styles.buttonText, { color }]}>{label}</Text>
  </Pressable>;
}

export function Field({ label, error, ...props }: TextInputProps & { label: string; error?: string }) {
  const theme = useTheme();
  return <View style={styles.field}><Text style={[styles.label, { color: theme.text }]}>{label}</Text>
    <TextInput accessibilityLabel={label} placeholderTextColor={theme.muted} {...props}
      style={[styles.input, { color: theme.text, borderColor: error ? theme.danger : theme.border, backgroundColor: theme.surface }]} />
    {error ? <Text accessibilityRole="alert" style={{ color: theme.danger }}>{error}</Text> : null}
  </View>;
}

const statusLabels: Record<OrderStatus, string> = {
  AWAITING_PAYMENT: "Awaiting payment", PAYMENT_FAILED: "Payment failed", PAYMENT_EXPIRED: "Payment expired",
  CONFIRMED: "Confirmed", PREPARING: "Preparing", OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered", CANCELLED: "Cancelled",
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  const theme = useTheme();
  const color = status === "CANCELLED" || status === "PAYMENT_FAILED" ? theme.danger
    : status === "DELIVERED" ? theme.success : status === "CONFIRMED" ? theme.warning : theme.primary;
  return <View accessibilityLabel={`Status: ${statusLabels[status]}`} style={[styles.badge, { borderColor: color }]}>
    <Text style={{ color, fontWeight: "700" }}>{statusLabels[status]}</Text>
  </View>;
}

export function StateMessage({ title, message, action }: { title: string; message?: string; action?: ReactNode }) {
  const theme = useTheme();
  return <View style={styles.state} accessibilityLiveRegion="polite"><Text style={[styles.stateTitle, { color: theme.text }]}>{title}</Text>
    {message ? <Text style={[styles.body, { color: theme.muted }]}>{message}</Text> : null}{action}</View>;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  const theme = useTheme();
  return <View style={styles.state} accessibilityLabel={label} accessibilityLiveRegion="polite"><ActivityIndicator color={theme.primary} /><Text style={{ color: theme.muted }}>{label}</Text></View>;
}

export const dsStyles = StyleSheet.create({
  page: { padding: spacing.md, gap: spacing.md }, row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  title: { fontSize: 26, fontWeight: "800" }, heading: { fontSize: 19, fontWeight: "700" }, body: { fontSize: 16, lineHeight: 23 },
});

const styles = StyleSheet.create({
  screen: { flex: 1 }, card: { padding: spacing.md, borderRadius: radii.md, borderWidth: 1, gap: spacing.sm },
  button: { minHeight: 48, borderRadius: radii.sm, borderWidth: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md },
  buttonText: { fontSize: 16, fontWeight: "700" }, field: { gap: spacing.xs }, label: { fontSize: 15, fontWeight: "600" },
  input: { minHeight: 48, borderWidth: 1, borderRadius: radii.sm, paddingHorizontal: spacing.md, fontSize: 16 },
  badge: { alignSelf: "flex-start", borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  state: { padding: spacing.xl, alignItems: "center", justifyContent: "center", gap: spacing.md },
  stateTitle: { fontSize: 20, fontWeight: "700", textAlign: "center" }, body: { fontSize: 16, textAlign: "center" },
});
