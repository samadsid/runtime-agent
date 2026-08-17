import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";

import { staffApi } from "@/app-services";
import { useAuth } from "@/auth/auth-context";
import { AppText, Button, ErrorState, MetricCard, ResponsiveGrid, Screen, SectionHeader, StateMessage, spacing, useResponsiveLayout, useTheme } from "@/design-system";
import { OrderRow } from "@/features/orders/order-row";
import { queryKeys } from "@/query/query-keys";

export default function DashboardScreen() {
  const theme = useTheme(); const router = useRouter(); const { horizontalPadding } = useResponsiveLayout();
  const { identity } = useAuth(); const admin = identity?.active_membership.role === "ADMIN";
  const query = useQuery({ queryKey: queryKeys.dashboard, queryFn: ({ signal }) => staffApi.dashboard(signal) });
  const inventory = useQuery({ queryKey: queryKeys.inventorySummary, queryFn: ({ signal }) => staffApi.inventorySummary(signal), enabled: admin });
  if (query.isPending) return <Screen><StateMessage title="Loading dashboard" message="Preparing the latest operational summary." /></Screen>;
  if (query.isError || !query.data) return <Screen><ErrorState title="Dashboard unavailable" message="The operational summary could not be loaded." action={<Button label="Retry" onPress={() => void query.refetch()} />} /></Screen>;
  const cards = [
    { label: "Confirmed", value: query.data.counts.confirmed, status: "CONFIRMED", icon: "checkmark-circle-outline" as const },
    { label: "Preparing", value: query.data.counts.preparing, status: "PREPARING", icon: "cube-outline" as const },
    { label: "Out for delivery", value: query.data.counts.out_for_delivery, status: "OUT_FOR_DELIVERY", icon: "car-outline" as const },
  ] as const;
  return <Screen><ScrollView refreshControl={<RefreshControl colors={[theme.colors.brand]} refreshing={query.isRefetching} onRefresh={() => { void query.refetch(); if (admin) void inventory.refetch(); }} />} contentContainerStyle={[styles.page, { paddingHorizontal: horizontalPadding }]}>
    <View><AppText variant="titleLarge" weight="bold">Fulfilment overview</AppText><AppText color="secondary">{identity?.display_name} · {identity?.active_membership.role.replaceAll("_", " ")}</AppText></View>
    <ResponsiveGrid minimumItemWidth={220}>{cards.map((card) => <MetricCard key={card.status} label={card.label} value={card.value} icon={card.icon} onPress={() => router.push({ pathname: "/(protected)/orders", params: { status: card.status } })} />)}</ResponsiveGrid>
    {admin ? <View style={styles.section}><SectionHeader title="Inventory risk" />{inventory.isError ? <ErrorState title="Inventory summary unavailable" action={<Button variant="secondary" label="Retry inventory" onPress={() => void inventory.refetch()} />} /> : inventory.data ? <ResponsiveGrid minimumItemWidth={220}><MetricCard label="Low stock" value={inventory.data.low_stock_products} tone="warning" icon="warning-outline" onPress={() => router.push({ pathname: "/(protected)/inventory", params: { stockState: "LOW" } } as never)} /><MetricCard label="Out of stock" value={inventory.data.out_of_stock_products} tone="warning" icon="alert-circle-outline" onPress={() => router.push({ pathname: "/(protected)/inventory", params: { stockState: "OUT" } } as never)} /></ResponsiveGrid> : null}</View> : null}
    <View style={styles.section}><SectionHeader title="Oldest confirmed" />{query.data.oldest_confirmed_orders.length ? query.data.oldest_confirmed_orders.map((order) => <OrderRow key={order.order_id} order={order} onPress={() => router.push(`/(protected)/orders/${order.order_id}`)} />) : <StateMessage title="No confirmed orders" message="The queue is clear." />}</View>
  </ScrollView></Screen>;
}
const styles = StyleSheet.create({ page: { width: "100%", maxWidth: 1440, alignSelf: "center", paddingVertical: spacing[4], paddingBottom: spacing[8], gap: spacing[6] }, section: { gap: spacing[3] } });
