import * as Crypto from "expo-crypto";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { StyleSheet } from "react-native";

import { staffApi } from "@/app-services";
import { AppText, Button, ErrorState, Loading, ResponsiveContainer, Screen, spacing } from "@/design-system";
import { ProductForm, type ProductFormValues } from "@/features/catalog/product-form";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";

export default function NewProductScreen() {
  const router = useRouter(); const options = useQuery({ queryKey: queryKeys.catalogOptions, queryFn: ({ signal }) => staffApi.catalogOptions(signal) });
  const mutation = useMutation({ mutationFn: (value: ProductFormValues) => staffApi.createProduct({ sku: value.sku.trim(), name: value.name.trim(), category_id: value.category_id, price: value.price, currency: value.currency, unit: value.unit, status: "INACTIVE", low_stock_threshold: value.low_stock_threshold || null, display_order: Number(value.display_order) }, Crypto.randomUUID()), onSuccess: (result) => { void queryClient.invalidateQueries({ queryKey: ["staff", "products"] }); router.replace(`/(protected)/catalog/${result.product.id}` as never); } });
  if (options.isPending) return <Screen><Loading label="Loading product options" /></Screen>; if (!options.data || options.isError) return <Screen><ErrorState title="Product options unavailable" action={<Button label="Retry" onPress={() => void options.refetch()} />} /></Screen>;
  return <Screen><ResponsiveContainer scroll contentStyle={styles.page}><AppText variant="titleLarge" weight="bold">Create product</AppText><AppText color="secondary">Products start inactive. Receive stock and review details before activation.</AppText><ProductForm options={options.data} busy={mutation.isPending} submitError={mutation.isError ? "Could not create the product. Your input is preserved." : undefined} onSubmit={(value) => mutation.mutate(value)} onCancel={() => router.back()} /></ResponsiveContainer></Screen>;
}
const styles = StyleSheet.create({ page: { maxWidth: 720, gap: spacing[3], paddingBottom: spacing[8] } });
