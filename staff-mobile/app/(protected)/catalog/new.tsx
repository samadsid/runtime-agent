import * as Crypto from "expo-crypto";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Controller, useForm } from "react-hook-form";
import { ScrollView, Text } from "react-native";
import { z } from "zod";
import { staffApi } from "@/app-services";
import { Button, Field, Loading, Screen, StateMessage, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";

const schema = z.object({ sku: z.string().trim().min(1), name: z.string().trim().min(1), price: z.string().regex(/^\d+(\.\d+)?$/), low_stock_threshold: z.string().regex(/^\d+(\.\d+)?$/).or(z.literal("")), display_order: z.string().regex(/^\d+$/) });
type Form = z.infer<typeof schema>;
export default function NewProductScreen() {
  const theme = useTheme(); const router = useRouter(); const options = useQuery({ queryKey: queryKeys.catalogOptions, queryFn: ({ signal }) => staffApi.catalogOptions(signal) });
  const form = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { sku: "", name: "", price: "", low_stock_threshold: "", display_order: "0" } });
  const mutation = useMutation({ mutationFn: (value: Form) => staffApi.createProduct({ sku: value.sku, name: value.name, category_id: null, price: value.price, currency: options.data!.currencies[0]!, unit: options.data!.units[0]!, status: "INACTIVE", low_stock_threshold: value.low_stock_threshold || null, display_order: Number(value.display_order) }, Crypto.randomUUID()), onSuccess: (result) => { void queryClient.invalidateQueries({ queryKey: ["staff", "products"] }); router.replace(`/(protected)/catalog/${result.product.id}` as never); } });
  if (options.isPending) return <Screen><Loading label="Loading product options" /></Screen>;
  if (!options.data || options.isError) return <Screen><StateMessage title="Product options unavailable" /></Screen>;
  return <Screen><ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md }} keyboardShouldPersistTaps="handled"><Text style={[dsStyles.title, { color: theme.text }]}>Create product</Text>{(["sku", "name", "price", "low_stock_threshold", "display_order"] as const).map((name) => <Controller key={name} control={form.control} name={name} render={({ field, fieldState }) => <Field label={name.replaceAll("_", " ")} value={field.value} onChangeText={field.onChange} keyboardType={name === "sku" || name === "name" ? "default" : "decimal-pad"} error={fieldState.error?.message} />} />)}<Text style={{ color: theme.muted }}>Currency: {options.data.currencies[0]} · Unit: {options.data.units[0]}. Add initial stock separately through Receive stock.</Text>{mutation.isError ? <Text style={{ color: theme.danger }}>Could not create product. Your input is preserved.</Text> : null}<Button label="Create inactive product" disabled={mutation.isPending} onPress={form.handleSubmit((value) => mutation.mutate(value))} /></ScrollView></Screen>;
}
