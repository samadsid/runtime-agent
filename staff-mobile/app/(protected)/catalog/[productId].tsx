import * as Crypto from "expo-crypto";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { StaffApiError } from "@/api/errors";
import { staffApi } from "@/app-services";
import { AppText, Banner, Button, Card, Confirmation, ErrorState, Inline, KeyValueRow, Loading, ResponsiveContainer, Screen, SectionHeader, StatusBadge, TextField, spacing } from "@/design-system";
import { presentProductStatus, presentStockState } from "@/features/presentation/status";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";

export default function ProductDetailScreen() {
  const { productId = "" } = useLocalSearchParams<{ productId: string }>(); const router = useRouter(); const [reason, setReason] = useState(""); const [confirming, setConfirming] = useState(false);
  const query = useQuery({ queryKey: queryKeys.product(productId), queryFn: ({ signal }) => staffApi.product(productId, signal) });
  const statusMutation = useMutation({ mutationFn: ({ next, reason }: { next: "ACTIVE" | "INACTIVE"; reason: string }) => staffApi.changeProductStatus(productId, next, reason, query.data!.product.version, Crypto.randomUUID()), onSuccess: (value) => { queryClient.setQueryData(queryKeys.product(productId), value); void queryClient.invalidateQueries({ queryKey: ["staff", "products"] }); void queryClient.invalidateQueries({ queryKey: queryKeys.inventorySummary }); setConfirming(false); setReason(""); }, onError: (error) => { setConfirming(false); if (error instanceof StaffApiError && ["stale_product_version", "conflict"].includes(error.code)) void query.refetch(); } });
  if (query.isPending) return <Screen><Loading label="Loading product" /></Screen>; if (!query.data || query.isError) return <Screen><ErrorState title="Product unavailable" action={<Button label="Retry" onPress={() => void query.refetch()} />} /></Screen>;
  const item = query.data; const next = item.product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE"; const lifecycle = presentProductStatus(item.product.status);
  return <Screen><ResponsiveContainer scroll contentStyle={styles.page}><Inline between style={styles.top}><View style={styles.flex}><AppText variant="titleLarge" weight="bold">{item.product.name}</AppText><AppText color="secondary">SKU {item.product.sku}</AppText></View><StatusBadge {...lifecycle} /></Inline>
    {statusMutation.isError ? <Banner tone="warning" message="The lifecycle change was not applied. Review the current product before trying again." /> : null}
    <Card><SectionHeader title="Selling" /><KeyValueRow label="Price" value={`${item.product.price} ${item.product.currency}/${item.product.unit}`} primary /><KeyValueRow label="Category" value={item.product.category_name ?? "Uncategorized"} /><KeyValueRow label="Display order" value={String(item.product.display_order)} /></Card>
    <Card variant="tonal"><SectionHeader title="Inventory balance" /><KeyValueRow label="Sellable" value={`${item.sellable_quantity} ${item.product.unit}`} primary /><KeyValueRow label="On hand" value={`${item.on_hand_quantity} ${item.product.unit}`} /><KeyValueRow label="Reserved" value={`${item.reserved_quantity} ${item.product.unit}`} />{item.stock_states.map((state) => <StatusBadge key={state} {...presentStockState(state)} />)}</Card>
    <View style={styles.actions}><Button label="Edit product" icon="create-outline" onPress={() => router.push(`/(protected)/catalog/${productId}/edit` as never)} /><Button variant="secondary" label="Inventory and movements" icon="cube-outline" onPress={() => router.push(`/(protected)/inventory/${productId}` as never)} /><Button variant={next === "INACTIVE" ? "danger" : "secondary"} label={next === "INACTIVE" ? "Deactivate product" : "Activate product"} onPress={() => setConfirming(true)} /></View>
  </ResponsiveContainer><Confirmation visible={confirming} title={`${next === "INACTIVE" ? "Deactivate" : "Activate"} ${item.product.name}?`} message={next === "INACTIVE" ? "The product will no longer be available to customers." : "The product becomes sellable only when its other availability rules pass."} confirmLabel={next === "INACTIVE" ? "Deactivate" : "Activate"} danger={next === "INACTIVE"} busy={statusMutation.isPending} onConfirm={() => { if (reason.trim()) statusMutation.mutate({ next, reason: reason.trim() }); }} onCancel={() => { setConfirming(false); setReason(""); }}><TextField label="Reason" required value={reason} onChangeText={setReason} multiline error={!reason.trim() ? "A reason is required." : undefined} /></Confirmation></Screen>;
}
const styles = StyleSheet.create({ page: { maxWidth: 900, gap: spacing[4], paddingBottom: spacing[8] }, top: { alignItems: "flex-start" }, flex: { flex: 1 }, actions: { gap: spacing[3] } });
