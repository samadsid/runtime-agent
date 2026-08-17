import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { StyleSheet, View } from "react-native";
import { z } from "zod";

import type { CatalogOptions } from "@/api/contracts";
import { AppText, Button, Card, FilterChip, SectionHeader, TextField, spacing } from "@/design-system";

const schema = z.object({
  sku: z.string().trim().min(1, "SKU is required."), name: z.string().trim().min(1, "Name is required."),
  category_id: z.string().nullable(), price: z.string().regex(/^\d+(\.\d+)?$/, "Enter a valid price."),
  currency: z.string().min(1), unit: z.string().min(1),
  low_stock_threshold: z.string().regex(/^\d+(\.\d+)?$/, "Enter a valid threshold.").or(z.literal("")),
  display_order: z.string().regex(/^\d+$/, "Enter a whole number."),
});
export type ProductFormValues = z.infer<typeof schema>;

export function ProductForm({ options, initial, editing = false, busy, submitError, onSubmit, onCancel }: {
  options: CatalogOptions; initial?: Partial<ProductFormValues>; editing?: boolean; busy?: boolean; submitError?: string;
  onSubmit(values: ProductFormValues): void; onCancel?(): void;
}) {
  const defaults: ProductFormValues = { sku: "", name: "", category_id: null, price: "", currency: options.currencies[0] ?? "", unit: options.units[0] ?? "", low_stock_threshold: "", display_order: "0", ...initial };
  const form = useForm<ProductFormValues>({ resolver: zodResolver(schema), defaultValues: defaults });
  return <View style={styles.form}>
    <Card variant="outlined"><SectionHeader title="Identity" /><Controller control={form.control} name="name" render={({ field, fieldState }) => <TextField label="Product name" required value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={fieldState.error?.message} />} /><Controller control={form.control} name="sku" render={({ field, fieldState }) => <TextField label="SKU" required editable={!editing} value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={fieldState.error?.message} help={editing ? "SKU cannot be changed after creation." : undefined} />} />
      <AppText variant="labelLarge" weight="semibold">Category</AppText><View style={styles.chips}><Controller control={form.control} name="category_id" render={({ field }) => <><FilterChip label="Uncategorized" selected={!field.value} onPress={() => field.onChange(null)} />{options.categories.map((category) => <FilterChip key={category.id} label={category.name} selected={field.value === category.id} onPress={() => field.onChange(category.id)} />)}</>} /></View></Card>
    <Card variant="outlined"><SectionHeader title="Selling" /><Controller control={form.control} name="price" render={({ field, fieldState }) => <TextField label="Price" required keyboardType="decimal-pad" value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={fieldState.error?.message} />} />
      <AppText variant="labelLarge" weight="semibold">Currency</AppText><View style={styles.chips}><Controller control={form.control} name="currency" render={({ field }) => <>{options.currencies.map((value) => <FilterChip key={value} label={value} selected={field.value === value} onPress={() => field.onChange(value)} />)}</>} /></View>
      <AppText variant="labelLarge" weight="semibold">Unit</AppText><View style={styles.chips}><Controller control={form.control} name="unit" render={({ field }) => <>{options.units.map((value) => <FilterChip key={value} label={value} selected={field.value === value} onPress={() => { if (!editing) field.onChange(value); }} />)}</>} /></View>{editing ? <AppText color="secondary">Unit is locked after creation to protect inventory history.</AppText> : null}</Card>
    <Card variant="outlined"><SectionHeader title="Availability" /><Controller control={form.control} name="low_stock_threshold" render={({ field, fieldState }) => <TextField label={`Low-stock threshold (${form.watch("unit")})`} keyboardType="decimal-pad" value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={fieldState.error?.message} help="Leave blank when no threshold is required." />} /><Controller control={form.control} name="display_order" render={({ field, fieldState }) => <TextField label="Display order" keyboardType="number-pad" value={field.value} onBlur={field.onBlur} onChangeText={field.onChange} error={fieldState.error?.message} /> } /></Card>
    {submitError ? <AppText color="danger" accessibilityRole="alert">{submitError}</AppText> : null}<Button label={editing ? "Save changes" : "Create inactive product"} loading={busy} onPress={form.handleSubmit(onSubmit)} />{onCancel ? <Button variant="tertiary" label="Cancel" onPress={onCancel} /> : null}
  </View>;
}
const styles = StyleSheet.create({ form: { gap: spacing[4] }, chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing[2] } });
