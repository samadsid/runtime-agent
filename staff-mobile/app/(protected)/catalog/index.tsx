import { useInfiniteQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import type { CatalogFilters } from "@/api/staff-api";
import { staffApi } from "@/app-services";
import { Button, Card, Field, Loading, Screen, StateMessage, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { queryKeys } from "@/query/query-keys";

export default function CatalogScreen() {
  const theme = useTheme(); const router = useRouter(); const [queryText, setQueryText] = useState("");
  const [status, setStatus] = useState<"ACTIVE" | "INACTIVE" | undefined>();
  const filters = useMemo<CatalogFilters>(() => ({ status, query: queryText.trim() || undefined }), [status, queryText]);
  const query = useInfiniteQuery({ queryKey: queryKeys.products(filters), queryFn: ({ pageParam, signal }) => staffApi.products(filters, pageParam, signal), initialPageParam: undefined as string | undefined, getNextPageParam: (last) => last.next_cursor ?? undefined });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return <Screen><FlatList data={items} keyExtractor={(item) => item.product.id} contentContainerStyle={styles.page}
    ListHeaderComponent={<View style={styles.gap}><Text style={[dsStyles.title, { color: theme.text }]}>Catalog</Text><Button label="Create product" onPress={() => router.push("/(protected)/catalog/new" as never)} /><Field label="Search name or SKU" value={queryText} onChangeText={setQueryText} /><View style={styles.row}>{([undefined, "ACTIVE", "INACTIVE"] as const).map((value) => <Pressable key={value ?? "ALL"} onPress={() => setStatus(value)} style={[styles.chip, { borderColor: status === value ? theme.primary : theme.border }]}><Text style={{ color: theme.text }}>{value ?? "ALL"}</Text></Pressable>)}</View></View>}
    renderItem={({ item }) => <Pressable onPress={() => router.push(`/(protected)/catalog/${item.product.id}` as never)}><Card><Text style={[dsStyles.heading, { color: theme.text }]}>{item.product.name}</Text><Text style={{ color: theme.muted }}>{item.product.sku} · {item.product.status}</Text><Text style={{ color: theme.text }}>{item.product.price} {item.product.currency}/{item.product.unit}</Text><Text style={{ color: theme.text }}>Sellable {item.sellable_quantity} · On hand {item.on_hand_quantity} · Reserved {item.reserved_quantity}</Text><Text style={{ color: theme.muted }}>{item.stock_states.join(" · ")}</Text></Card></Pressable>}
    ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />} ListEmptyComponent={query.isPending ? <Loading label="Loading catalog" /> : query.isError ? <StateMessage title="Catalog unavailable" action={<Button label="Retry" onPress={() => void query.refetch()} />} /> : <StateMessage title="No products" />}
    refreshing={query.isRefetching && !query.isFetchingNextPage} onRefresh={() => void query.refetch()} onEndReached={() => { if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage(); }} />
  </Screen>;
}
const styles = StyleSheet.create({ page: { padding: spacing.md, paddingBottom: spacing.xl }, gap: { gap: spacing.md, marginBottom: spacing.md }, row: { flexDirection: "row", gap: spacing.sm }, chip: { borderWidth: 2, borderRadius: 999, padding: 10 } });
