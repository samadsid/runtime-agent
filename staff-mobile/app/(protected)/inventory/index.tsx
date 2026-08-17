import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";

import { staffApi } from "@/app-services";
import { AppText, Button, Card, ErrorState, KeyValueRow, Loading, MetricCard, ResponsiveGrid, Screen, SectionHeader, StateMessage, StatusBadge, spacing, useResponsiveLayout, useTheme } from "@/design-system";
import { presentStockState } from "@/features/presentation/status";
import { queryKeys } from "@/query/query-keys";

export default function InventoryScreen() {
  const theme = useTheme(); const { horizontalPadding } = useResponsiveLayout(); const router = useRouter(); const params = useLocalSearchParams<{ stockState?: "LOW" | "OUT" }>(); const stockState = params.stockState ?? "LOW";
  const summary = useQuery({ queryKey: queryKeys.inventorySummary, queryFn: ({ signal }) => staffApi.inventorySummary(signal) });
  const products = useQuery({ queryKey: queryKeys.products({ stockState }), queryFn: ({ signal }) => staffApi.products({ stockState }, undefined, signal) });
  if (summary.isPending || products.isPending) return <Screen><Loading label="Loading inventory" /></Screen>;
  if (!summary.data || !products.data) return <Screen><ErrorState title="Inventory unavailable" action={<Button label="Retry" onPress={() => { void summary.refetch(); void products.refetch(); }} />} /></Screen>;
  return <Screen><ScrollView contentContainerStyle={[styles.page, { paddingHorizontal: horizontalPadding }]}><SectionHeader title="Inventory" />
    <ResponsiveGrid minimumItemWidth={200}><MetricCard label="Active products" value={summary.data.active_products} tone="success" icon="checkmark-circle-outline" /><MetricCard label="Low stock" value={summary.data.low_stock_products} tone="warning" icon="warning-outline" onPress={() => router.setParams({ stockState: "LOW" })} /><MetricCard label="Out of stock" value={summary.data.out_of_stock_products} tone="warning" icon="alert-circle-outline" onPress={() => router.setParams({ stockState: "OUT" })} /><MetricCard label="Inactive" value={summary.data.inactive_products} icon="pause-circle-outline" /></ResponsiveGrid>
    <SectionHeader title={stockState === "OUT" ? "Out-of-stock products" : "Low-stock products"} />{products.data.items.length ? products.data.items.map((item) => <Card key={item.product.id} variant="interactive" onPress={() => router.push(`/(protected)/inventory/${item.product.id}` as never)} accessibilityLabel={`Manage stock for ${item.product.name}`}><AppText variant="titleSmall" weight="bold">{item.product.name}</AppText><KeyValueRow label="Sellable" value={`${item.sellable_quantity} ${item.product.unit}`} primary /><KeyValueRow label="On hand" value={`${item.on_hand_quantity} ${item.product.unit}`} /><KeyValueRow label="Reserved" value={`${item.reserved_quantity} ${item.product.unit}`} />{item.stock_states.map((state) => <StatusBadge key={state} {...presentStockState(state)} />)}</Card>) : <StateMessage title={`No ${stockState === "OUT" ? "out-of-stock" : "low-stock"} products`} message="No products currently match this risk filter." />}</ScrollView></Screen>;
}
const styles = StyleSheet.create({ page: { width: "100%", maxWidth: 1440, alignSelf: "center", paddingVertical: spacing[4], paddingBottom: spacing[8], gap: spacing[4] } });
