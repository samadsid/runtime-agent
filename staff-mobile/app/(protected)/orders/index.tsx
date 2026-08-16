import { useInfiniteQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { z } from "zod";

import { orderStatusSchema, type OrderStatus } from "@/api/contracts";
import type { OrderFilters } from "@/api/staff-api";
import { staffApi } from "@/app-services";
import { Button, Field, Loading, Screen, StateMessage, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { OrderRow } from "@/features/orders/order-row";
import { buildDateRange } from "@/features/orders/date-range";
import { mergeOrderPages } from "@/features/orders/pagination";
import { queryKeys } from "@/query/query-keys";

const operationalStatuses: OrderStatus[] = ["CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"];
const uuidSchema = z.string().uuid();

export default function OrdersScreen() {
  const theme = useTheme(); const router = useRouter(); const params = useLocalSearchParams<{ status?: string }>();
  const initialStatus = orderStatusSchema.safeParse(params.status).success ? params.status as OrderStatus : undefined;
  const [status, setStatus] = useState<OrderStatus | undefined>(initialStatus);
  const [reference, setReference] = useState(""); const [debouncedReference, setDebouncedReference] = useState("");
  const [createdFrom, setCreatedFrom] = useState(""); const [createdTo, setCreatedTo] = useState("");
  useEffect(() => { const timer = setTimeout(() => setDebouncedReference(reference.trim()), 350); return () => clearTimeout(timer); }, [reference]);
  useEffect(() => { if (initialStatus) setStatus(initialStatus); }, [initialStatus]);
  const referenceError = debouncedReference && !uuidSchema.safeParse(debouncedReference).success ? "Enter the complete order reference." : undefined;
  const dateRange = buildDateRange(createdFrom, createdTo);
  const filters = useMemo<OrderFilters>(() => ({
    status,
    orderReference: referenceError ? undefined : debouncedReference || undefined,
    createdFrom: dateRange.createdFrom,
    createdTo: dateRange.createdTo,
  }), [status, debouncedReference, referenceError, dateRange.createdFrom, dateRange.createdTo]);
  const query = useInfiniteQuery({
    queryKey: queryKeys.orders(filters),
    queryFn: ({ pageParam, signal }) => staffApi.orders(filters, pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !referenceError && !dateRange.error,
  });
  const orders = useMemo(() => mergeOrderPages(query.data?.pages), [query.data]);
  const clear = () => { setStatus(undefined); setReference(""); setDebouncedReference(""); setCreatedFrom(""); setCreatedTo(""); };
  return <Screen><FlatList data={orders} keyExtractor={(item) => item.order_id} contentContainerStyle={styles.page}
    ListHeaderComponent={<View style={styles.filters}><Text style={[dsStyles.title, { color: theme.text }]}>Orders</Text>
      <Field label="Exact order reference" value={reference} onChangeText={setReference} autoCapitalize="none" error={referenceError} />
      <View style={styles.dateRow}><View style={{ flex: 1 }}><Field label="From (YYYY-MM-DD)" value={createdFrom} onChangeText={setCreatedFrom} error={dateRange.error} /></View><View style={{ flex: 1 }}><Field label="To (YYYY-MM-DD)" value={createdTo} onChangeText={setCreatedTo} /></View></View>
      <View style={styles.chips}><Pressable onPress={() => setStatus(undefined)} style={[styles.chip, { borderColor: !status ? theme.primary : theme.border }]}><Text style={{ color: theme.text }}>All</Text></Pressable>{operationalStatuses.map((value) => <Pressable key={value} onPress={() => setStatus(value)} style={[styles.chip, { borderColor: status === value ? theme.primary : theme.border }]}><Text style={{ color: theme.text }}>{value.replaceAll("_", " ")}</Text></Pressable>)}</View>
      <Button variant="secondary" label="Clear filters" onPress={clear} />
    </View>}
    renderItem={({ item }) => <OrderRow order={item} onPress={() => router.push(`/(protected)/orders/${item.order_id}`)} />}
    ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
    ListEmptyComponent={query.isPending ? <Loading label="Loading orders" /> : query.isError ? <StateMessage title="Orders unavailable" action={<Button label="Retry" onPress={() => void query.refetch()} />} /> : <StateMessage title="No matching orders" message="Try clearing or changing the filters." />}
    ListFooterComponent={query.isFetchingNextPage ? <Loading label="Loading more orders" /> : null}
    refreshing={query.isRefetching && !query.isFetchingNextPage} onRefresh={() => void query.refetch()}
    onEndReached={() => { if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage(); }} onEndReachedThreshold={0.4} />
  </Screen>;
}
const styles = StyleSheet.create({ page: { padding: spacing.md, paddingBottom: spacing.xl }, filters: { gap: spacing.md, marginBottom: spacing.md }, dateRow: { flexDirection: "row", gap: spacing.sm }, chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }, chip: { borderWidth: 2, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 10, minHeight: 44, justifyContent: "center" } });
