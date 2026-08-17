import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";

import type { CatalogFilters } from "@/api/staff-api";
import { staffApi } from "@/app-services";
import { AppText, Button, Card, ErrorState, FilterChip, Inline, KeyValueRow, Loading, SearchField, SectionHeader, StateMessage, StatusBadge, spacing, useResponsiveLayout, useTheme } from "@/design-system";
import { presentProductStatus, presentStockState } from "@/features/presentation/status";
import { queryKeys } from "@/query/query-keys";

export default function CatalogScreen() {
  const theme = useTheme(); const { horizontalPadding } = useResponsiveLayout(); const router = useRouter(); const [queryText, setQueryText] = useState("");
  const [status, setStatus] = useState<"ACTIVE" | "INACTIVE" | undefined>(); const [stockState, setStockState] = useState<"LOW" | "OUT" | undefined>(); const [categoryId, setCategoryId] = useState<string | undefined>();
  const filters = useMemo<CatalogFilters>(() => ({ status, stockState, categoryId, query: queryText.trim() || undefined }), [status, stockState, categoryId, queryText]);
  const options = useQuery({ queryKey: queryKeys.catalogOptions, queryFn: ({ signal }) => staffApi.catalogOptions(signal) });
  const query = useInfiniteQuery({ queryKey: queryKeys.products(filters), queryFn: ({ pageParam, signal }) => staffApi.products(filters, pageParam, signal), initialPageParam: undefined as string | undefined, getNextPageParam: (last) => last.next_cursor ?? undefined });
  const items = query.data?.pages.flatMap((page) => page.items) ?? []; const filtered = Boolean(status || stockState || categoryId || queryText);
  const clear = () => { setStatus(undefined); setStockState(undefined); setCategoryId(undefined); setQueryText(""); };
  return <FlatList style={{ backgroundColor: theme.colors.background }} data={items} keyExtractor={(item) => item.product.id} contentContainerStyle={[styles.page, { paddingHorizontal: horizontalPadding }]}
    ListHeaderComponent={<View style={styles.header}><SectionHeader title="Catalog" action={<Button label="Add product" icon="add-outline" onPress={() => router.push("/(protected)/catalog/new" as never)} />} /><SearchField label="Search name or SKU" value={queryText} onChangeText={setQueryText} />
      <AppText variant="labelLarge" weight="semibold">Lifecycle</AppText><View style={styles.chips}>{([undefined, "ACTIVE", "INACTIVE"] as const).map((value) => <FilterChip key={value ?? "ALL"} label={value ? presentProductStatus(value).label : "All"} selected={status === value} onPress={() => setStatus(value)} />)}</View>
      <AppText variant="labelLarge" weight="semibold">Stock</AppText><View style={styles.chips}>{([undefined, "LOW", "OUT"] as const).map((value) => <FilterChip key={value ?? "ALL"} label={value ? presentStockState(value).label : "Any stock"} selected={stockState === value} onPress={() => setStockState(value)} />)}</View>
      {options.data?.categories.length ? <><AppText variant="labelLarge" weight="semibold">Category</AppText><View style={styles.chips}><FilterChip label="All categories" selected={!categoryId} onPress={() => setCategoryId(undefined)} />{options.data.categories.map((category) => <FilterChip key={category.id} label={category.name} selected={categoryId === category.id} onPress={() => setCategoryId(category.id)} />)}</View></> : null}
      {filtered ? <Button variant="tertiary" label="Clear filters" icon="close-outline" onPress={clear} /> : null}</View>}
    renderItem={({ item }) => { const lifecycle = presentProductStatus(item.product.status); return <Card variant="interactive" onPress={() => router.push(`/(protected)/catalog/${item.product.id}` as never)} accessibilityLabel={`${item.product.name}, ${lifecycle.label}`}><Inline between style={styles.top}><View style={styles.flex}><AppText variant="titleSmall" weight="bold">{item.product.name}</AppText><AppText color="secondary">SKU {item.product.sku}</AppText></View><StatusBadge {...lifecycle} /></Inline><KeyValueRow label="Price" value={`${item.product.price} ${item.product.currency}/${item.product.unit}`} /><KeyValueRow label="Sellable" value={`${item.sellable_quantity} ${item.product.unit}`} primary /><KeyValueRow label="On hand · Reserved" value={`${item.on_hand_quantity} · ${item.reserved_quantity}`} />{item.stock_states.map((stock) => <StatusBadge key={stock} {...presentStockState(stock)} />)}</Card>; }}
    ItemSeparatorComponent={() => <View style={styles.separator} />} ListEmptyComponent={query.isPending ? <Loading label="Loading catalog" /> : query.isError ? <ErrorState title="Catalog unavailable" action={<Button label="Retry" onPress={() => void query.refetch()} />} /> : <StateMessage title={filtered ? "No matching products" : "No products"} message={filtered ? "Clear or change filters to broaden the catalog." : "Create a product to begin managing the catalog."} action={filtered ? <Button variant="secondary" label="Clear filters" onPress={clear} /> : undefined} />}
    ListFooterComponent={query.isFetchingNextPage ? <Loading label="Loading more products" /> : null} refreshing={query.isRefetching && !query.isFetchingNextPage} onRefresh={() => void query.refetch()} onEndReached={() => { if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage(); }} />;
}
const styles = StyleSheet.create({ page: { width: "100%", maxWidth: 1440, alignSelf: "center", paddingVertical: spacing[4], paddingBottom: spacing[8] }, header: { gap: spacing[3], marginBottom: spacing[4] }, chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing[2] }, top: { alignItems: "flex-start" }, flex: { flex: 1 }, separator: { height: spacing[2] } });
