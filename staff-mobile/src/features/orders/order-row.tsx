import { Pressable, StyleSheet, Text, View } from "react-native";

import type { OrderListItem } from "@/api/contracts";
import { Card, StatusBadge, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { formatDateTime, formatMoney } from "@/features/orders/presentation";

export function OrderRow({ order, onPress }: { order: OrderListItem; onPress(): void }) {
  const theme = useTheme();
  return <Pressable accessibilityRole="button" accessibilityHint="Opens order details" onPress={onPress}>
    <Card><View style={styles.between}><Text style={[dsStyles.heading, { color: theme.text }]} numberOfLines={1}>{order.order_reference}</Text><StatusBadge status={order.status} /></View>
      <Text style={[dsStyles.body, { color: theme.text }]}>{order.customer_name} · {order.masked_phone_number}</Text>
      <View style={styles.between}><Text style={{ color: theme.text, fontWeight: "700" }}>{formatMoney(order.total, order.currency)}</Text><Text style={{ color: theme.muted }}>{formatDateTime(order.updated_at)}</Text></View>
    </Card>
  </Pressable>;
}
const styles = StyleSheet.create({ between: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm } });
