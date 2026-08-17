import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { staffApi } from "@/app-services";
import { Button, Card, Loading, Screen, StateMessage, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { OrderRow } from "@/features/orders/order-row";
import { queryKeys } from "@/query/query-keys";
import { useAuth } from "@/auth/auth-context";

export default function DashboardScreen() {
  const theme = useTheme(); const router = useRouter();
  const { identity } = useAuth(); const admin = identity?.active_membership.role === "ADMIN";
  const query = useQuery({ queryKey: queryKeys.dashboard, queryFn: ({ signal }) => staffApi.dashboard(signal) });
  const inventory = useQuery({ queryKey: queryKeys.inventorySummary, queryFn: ({ signal }) => staffApi.inventorySummary(signal), enabled: admin });
  if (query.isPending) return <Screen><Loading label="Loading dashboard" /></Screen>;
  if (query.isError || !query.data) return <Screen><StateMessage title="Dashboard unavailable" message="The operational summary could not be loaded." action={<Button label="Retry" onPress={() => void query.refetch()} />} /></Screen>;
  const cards = [
    ["Confirmed", query.data.counts.confirmed, "CONFIRMED"], ["Preparing", query.data.counts.preparing, "PREPARING"],
    ["Out for delivery", query.data.counts.out_for_delivery, "OUT_FOR_DELIVERY"],
  ] as const;
  return <Screen><ScrollView refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />} contentContainerStyle={styles.page}>
    <Text style={[dsStyles.title, { color: theme.text }]}>Fulfilment overview</Text>
    <View style={styles.cards}>{cards.map(([label, count, status]) => <View key={status} style={styles.summary}><Card><Text style={[styles.count, { color: theme.text }]}>{count}</Text><Text style={{ color: theme.muted }}>{label}</Text><Button variant="secondary" label={`View ${label.toLowerCase()}`} onPress={() => router.push({ pathname: "/(protected)/orders", params: { status } })} /></Card></View>)}</View>
    <Text style={[dsStyles.heading, { color: theme.text }]}>Oldest confirmed</Text>
    {admin && inventory.data ? <View style={styles.cards}><Card><Text style={[styles.count, { color: theme.text }]}>{inventory.data.low_stock_products}</Text><Text style={{ color: theme.muted }}>Low stock</Text><Button variant="secondary" label="View low stock" onPress={() => router.push({ pathname: "/(protected)/inventory", params: { stockState: "LOW" } } as never)} /></Card><Card><Text style={[styles.count, { color: theme.text }]}>{inventory.data.out_of_stock_products}</Text><Text style={{ color: theme.muted }}>Out of stock</Text><Button variant="secondary" label="View out of stock" onPress={() => router.push({ pathname: "/(protected)/inventory", params: { stockState: "OUT" } } as never)} /></Card></View> : null}
    {query.data.oldest_confirmed_orders.length ? query.data.oldest_confirmed_orders.map((order) => <OrderRow key={order.order_id} order={order} onPress={() => router.push(`/(protected)/orders/${order.order_id}`)} />) : <StateMessage title="No confirmed orders" message="The queue is clear." />}
  </ScrollView></Screen>;
}
const styles = StyleSheet.create({ page: { padding: spacing.md, gap: spacing.md }, cards: { gap: spacing.sm }, summary: { minWidth: "100%" }, count: { fontSize: 32, fontWeight: "800" } });
