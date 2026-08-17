import * as Crypto from "expo-crypto";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { StyleSheet } from "react-native";

import { StaffApiError } from "@/api/errors";
import { staffApi } from "@/app-services";
import { AppText, Button, ErrorState, Loading, ResponsiveContainer, Screen, spacing } from "@/design-system";
import { ProductForm, type ProductFormValues } from "@/features/catalog/product-form";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";

export default function EditProductScreen() {
  const { productId = "" } = useLocalSearchParams<{ productId: string }>(); const router = useRouter();
  const product = useQuery({ queryKey: queryKeys.product(productId), queryFn: ({ signal }) => staffApi.product(productId, signal) });
  const options = useQuery({ queryKey: queryKeys.catalogOptions, queryFn: ({ signal }) => staffApi.catalogOptions(signal) });
  const mutation = useMutation({ mutationFn: (value: ProductFormValues) => staffApi.updateProduct(productId, { name: value.name.trim(), category_id: value.category_id, price: value.price, low_stock_threshold: value.low_stock_threshold || null, display_order: Number(value.display_order) }, product.data!.product.version, Crypto.randomUUID()), onSuccess: (value) => { queryClient.setQueryData(queryKeys.product(productId), value); void queryClient.invalidateQueries({ queryKey: ["staff", "products"] }); router.back(); }, onError: (error) => { if (error instanceof StaffApiError && ["stale_product_version", "conflict"].includes(error.code)) void product.refetch(); } });
  if (product.isPending || options.isPending) return <Screen><Loading label="Loading product" /></Screen>; if (!product.data || !options.data || product.isError || options.isError) return <Screen><ErrorState title="Product unavailable" action={<Button label="Retry" onPress={() => { void product.refetch(); void options.refetch(); }} />} /></Screen>;
  const current = product.data.product;
  const conflict = mutation.error instanceof StaffApiError && ["stale_product_version", "conflict"].includes(mutation.error.code);
  return <Screen><ResponsiveContainer scroll contentStyle={styles.page}><AppText variant="titleLarge" weight="bold">Edit product</AppText>{conflict ? <AppText color="warning" accessibilityRole="alert">Another staff member changed this product. Current values were refreshed; review them before saving again.</AppText> : null}<ProductForm key={current.version} editing options={options.data} initial={{ sku: current.sku, name: current.name, category_id: current.category_id, price: current.price, currency: current.currency, unit: current.unit, low_stock_threshold: current.low_stock_threshold ?? "", display_order: String(current.display_order) }} busy={mutation.isPending} submitError={mutation.isError && !conflict ? "Could not save changes. Your input is preserved." : undefined} onSubmit={(value) => mutation.mutate(value)} onCancel={() => router.back()} /></ResponsiveContainer></Screen>;
}
const styles = StyleSheet.create({ page: { maxWidth: 720, gap: spacing[4], paddingBottom: spacing[8] } });
