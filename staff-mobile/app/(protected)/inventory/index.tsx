import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { staffApi } from "@/app-services";
import { Button, Card, Loading, Screen, StateMessage, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { queryKeys } from "@/query/query-keys";
export default function InventoryScreen() {
  const theme = useTheme(); const router = useRouter(); const params = useLocalSearchParams<{ stockState?: "LOW" | "OUT" }>();
  const summary = useQuery({ queryKey: queryKeys.inventorySummary, queryFn: ({ signal }) => staffApi.inventorySummary(signal) });
  const products = useQuery({ queryKey: queryKeys.products({ stockState: params.stockState ?? "LOW" }), queryFn: ({ signal }) => staffApi.products({ stockState: params.stockState ?? "LOW" }, undefined, signal) });
  if (summary.isPending || products.isPending) return <Screen><Loading label="Loading inventory" /></Screen>;
  if (!summary.data || !products.data) return <Screen><StateMessage title="Inventory unavailable" /></Screen>;
  return <Screen><ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}><Text style={[dsStyles.title, { color: theme.text }]}>Inventory</Text><View style={{ gap: spacing.sm }}><Card><Text style={{ color: theme.text }}>Low stock: {summary.data.low_stock_products}</Text><Text style={{ color: theme.text }}>Out of stock: {summary.data.out_of_stock_products}</Text></Card></View>{products.data.items.map((item) => <Card key={item.product.id}><Text style={[dsStyles.heading, { color: theme.text }]}>{item.product.name}</Text><Text style={{ color: theme.text }}>Sellable {item.sellable_quantity} {item.product.unit}</Text><Button label="Manage stock" onPress={() => router.push(`/(protected)/inventory/${item.product.id}` as never)} /></Card>)}</ScrollView></Screen>;
}
