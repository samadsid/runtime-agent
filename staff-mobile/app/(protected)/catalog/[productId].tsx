import * as Crypto from "expo-crypto";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, Text } from "react-native";
import { staffApi } from "@/app-services";
import { Button, Card, Field, Loading, Screen, StateMessage, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";
export default function ProductDetailScreen() {
  const { productId = "" } = useLocalSearchParams<{ productId: string }>(); const theme = useTheme(); const router = useRouter();
  const [reason, setReason] = useState("");
  const query = useQuery({ queryKey: queryKeys.product(productId), queryFn: ({ signal }) => staffApi.product(productId, signal) });
  const status = useMutation({ mutationFn: ({ next, reason }: { next: "ACTIVE" | "INACTIVE"; reason: string }) => staffApi.changeProductStatus(productId, next, reason, query.data!.product.version, Crypto.randomUUID()), onSuccess: (value) => { queryClient.setQueryData(queryKeys.product(productId), value); void queryClient.invalidateQueries({ queryKey: ["staff", "products"] }); void queryClient.invalidateQueries({ queryKey: queryKeys.inventorySummary }); } });
  if (query.isPending) return <Screen><Loading label="Loading product" /></Screen>; if (!query.data || query.isError) return <Screen><StateMessage title="Product unavailable" /></Screen>;
  const item = query.data; const next = item.product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
  return <Screen><ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}><Text style={[dsStyles.title, { color: theme.text }]}>{item.product.name}</Text><Card><Text style={{ color: theme.text }}>SKU {item.product.sku}</Text><Text style={{ color: theme.text }}>{item.product.price} {item.product.currency}/{item.product.unit}</Text><Text style={{ color: theme.text }}>Status {item.product.status} · version {item.product.version}</Text><Text style={{ color: theme.text }}>On hand {item.on_hand_quantity} · Reserved {item.reserved_quantity} · Sellable {item.sellable_quantity}</Text></Card><Button label="Edit product" onPress={() => router.push(`/(protected)/catalog/${productId}/edit` as never)} /><Button label="Inventory and movements" onPress={() => router.push(`/(protected)/inventory/${productId}` as never)} /><Field label={`${next === "INACTIVE" ? "Deactivation" : "Activation"} reason`} value={reason} onChangeText={setReason} multiline /><Button variant={next === "INACTIVE" ? "destructive" : "secondary"} label={next === "INACTIVE" ? "Deactivate" : "Activate"} disabled={status.isPending || !reason.trim()} onPress={() => status.mutate({ next, reason: reason.trim() })} /></ScrollView></Screen>;
}
