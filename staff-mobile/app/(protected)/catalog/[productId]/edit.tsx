import * as Crypto from "expo-crypto";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Text } from "react-native";
import { staffApi } from "@/app-services";
import { Button, Field, Loading, Screen, StateMessage, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";

export default function EditProductScreen() {
  const { productId = "" } = useLocalSearchParams<{ productId: string }>(); const router = useRouter(); const theme = useTheme();
  const product = useQuery({ queryKey: queryKeys.product(productId), queryFn: ({ signal }) => staffApi.product(productId, signal) });
  const [name, setName] = useState(""); const [price, setPrice] = useState(""); const [threshold, setThreshold] = useState("");
  useEffect(() => { if (product.data) { setName(product.data.product.name); setPrice(product.data.product.price); setThreshold(product.data.product.low_stock_threshold ?? ""); } }, [product.data]);
  const mutation = useMutation({ mutationFn: () => staffApi.updateProduct(productId, { name: name.trim(), price, low_stock_threshold: threshold || null }, product.data!.product.version, Crypto.randomUUID()), onSuccess: (value) => { queryClient.setQueryData(queryKeys.product(productId), value); void queryClient.invalidateQueries({ queryKey: ["staff", "products"] }); router.back(); }, onError: () => { void product.refetch(); } });
  if (product.isPending) return <Screen><Loading label="Loading product" /></Screen>; if (!product.data) return <Screen><StateMessage title="Product unavailable" /></Screen>;
  const valid = name.trim() && /^\d+(\.\d+)?$/.test(price) && (!threshold || /^\d+(\.\d+)?$/.test(threshold));
  return <Screen><ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md }} keyboardShouldPersistTaps="handled"><Text style={[dsStyles.title, { color: theme.text }]}>Edit product</Text><Field label="Name" value={name} onChangeText={setName} /><Field label={`Price (${product.data.product.currency})`} value={price} onChangeText={setPrice} keyboardType="decimal-pad" /><Field label={`Low-stock threshold (${product.data.product.unit})`} value={threshold} onChangeText={setThreshold} keyboardType="decimal-pad" /><Text style={{ color: theme.muted }}>Current product version {product.data.product.version}. A conflict refreshes current values and requires review.</Text><Button label="Save changes" disabled={!valid || mutation.isPending} onPress={() => mutation.mutate()} /></ScrollView></Screen>;
}
