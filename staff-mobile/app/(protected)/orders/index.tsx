import { useInfiniteQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { z } from "zod";

import { orderStatusSchema, type OrderStatus } from "@/api/contracts";
import type { OrderFilters } from "@/api/staff-api";
import { staffApi } from "@/app-services";
import { AppText, Button, ErrorState, FilterChip, Loading, SearchField, SectionHeader, StateMessage, TextField, spacing, useResponsiveLayout, useTheme } from "@/design-system";
import { buildDateRange } from "@/features/orders/date-range";
import { OrderRow } from "@/features/orders/order-row";
import { mergeOrderPages } from "@/features/orders/pagination";
import { presentOrderStatus } from "@/features/presentation/status";
import { queryKeys } from "@/query/query-keys";

const operationalStatuses: OrderStatus[] = ["CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"];
const publicOrderNumberSchema = z.string().regex(/^[A-Z0-9]{1,8}-[0-9]{6}-[0-9]{4,}$/);

export default function OrdersScreen() {
  const theme = useTheme(); const router = useRouter(); const { horizontalPadding, compact } = useResponsiveLayout(); const params = useLocalSearchParams<{ status?: string }>();
  const initialStatus = orderStatusSchema.safeParse(params.status).success ? params.status as OrderStatus : undefined;
  const [status, setStatus] = useState<OrderStatus | undefined>(initialStatus);
  const [reference, setReference] = useState(""); const [debouncedReference, setDebouncedReference] = useState("");
  const [createdFrom, setCreatedFrom] = useState(""); const [createdTo, setCreatedTo] = useState("");
  useEffect(() => { const timer = setTimeout(() => setDebouncedReference(reference.trim()), 350); return () => clearTimeout(timer); }, [reference]);
  useEffect(() => { if (initialStatus) setStatus(initialStatus); }, [initialStatus]);
  const normalizedReference = debouncedReference.toUpperCase();
  const referenceError = normalizedReference && !publicOrderNumberSchema.safeParse(normalizedReference).success ? "Enter a complete order number, for example MU-260818-0042." : undefined;
  const dateRange = buildDateRange(createdFrom, createdTo);
  const filters = useMemo<OrderFilters>(() => ({ status, orderReference: referenceError ? undefined : normalizedReference || undefined, createdFrom: dateRange.createdFrom, createdTo: dateRange.createdTo }), [status, normalizedReference, referenceError, dateRange.createdFrom, dateRange.createdTo]);
  const query = useInfiniteQuery({ queryKey: queryKeys.orders(filters), queryFn: ({ pageParam, signal }) => staffApi.orders(filters, pageParam, signal), initialPageParam: undefined as string | undefined, getNextPageParam: (last) => last.next_cursor ?? undefined, enabled: !referenceError && !dateRange.error });
  const orders = useMemo(() => mergeOrderPages(query.data?.pages), [query.data]);
  const filtered = Boolean(status || reference || createdFrom || createdTo);
  const clear = () => { setStatus(undefined); setReference(""); setDebouncedReference(""); setCreatedFrom(""); setCreatedTo(""); };
  return <FlatList style={{ backgroundColor: theme.colors.background }} data={orders} keyExtractor={(item) => item.order_id} contentContainerStyle={[styles.page, { paddingHorizontal: horizontalPadding }]}
    ListHeaderComponent={<View style={styles.filters}><SectionHeader title="Orders" /><SearchField label="Exact order reference" value={reference} onChangeText={setReference} autoCapitalize="none" error={referenceError} />
      <View style={compact ? styles.stack : styles.dateRow}><View style={styles.flex}><TextField label="From (YYYY-MM-DD)" value={createdFrom} onChangeText={setCreatedFrom} error={dateRange.error} /></View><View style={styles.flex}><TextField label="To (YYYY-MM-DD)" value={createdTo} onChangeText={setCreatedTo} /></View></View>
      <View style={styles.chips}><FilterChip label="All" selected={!status} onPress={() => setStatus(undefined)} />{operationalStatuses.map((value) => <FilterChip key={value} label={presentOrderStatus(value).label} selected={status === value} onPress={() => setStatus(value)} />)}</View>{filtered ? <Button variant="tertiary" label="Clear filters" icon="close-outline" onPress={clear} /> : null}</View>}
    renderItem={({ item }) => <OrderRow order={item} onPress={() => router.push(`/(protected)/orders/${item.order_id}`)} />}
    ItemSeparatorComponent={() => <View style={styles.separator} />}
    ListEmptyComponent={query.isPending ? <Loading label="Loading orders" /> : query.isError ? <ErrorState title="Orders unavailable" action={<Button label="Retry" onPress={() => void query.refetch()} />} /> : <StateMessage title={filtered ? "No matching orders" : "No orders"} message={filtered ? "Clear or change the filters to broaden the queue." : "Orders will appear here when they are placed."} action={filtered ? <Button variant="secondary" label="Clear filters" onPress={clear} /> : undefined} />}
    ListFooterComponent={query.isFetchingNextPage ? <Loading label="Loading more orders" /> : query.hasNextPage ? <AppText color="secondary" align="center">Scroll to load more</AppText> : null}
    refreshing={query.isRefetching && !query.isFetchingNextPage} onRefresh={() => void query.refetch()} onEndReached={() => { if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage(); }} onEndReachedThreshold={0.4} />;
}
const styles = StyleSheet.create({ page: { width: "100%", maxWidth: 1440, alignSelf: "center", paddingVertical: spacing[4], paddingBottom: spacing[8] }, filters: { gap: spacing[4], marginBottom: spacing[4] }, dateRow: { flexDirection: "row", gap: spacing[3] }, stack: { gap: spacing[3] }, flex: { flex: 1 }, chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing[2] }, separator: { height: spacing[2] } });
