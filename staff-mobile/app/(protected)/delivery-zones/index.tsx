import { useInfiniteQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";

import { staffApi } from "@/app-services";
import { AppText, Button, Card, ErrorState, FilterChip, Inline, KeyValueRow, Loading, SectionHeader, StateMessage, StatusBadge, spacing, useResponsiveLayout, useTheme } from "@/design-system";
import { queryKeys } from "@/query/query-keys";

const statuses = [undefined, "DRAFT", "ACTIVE", "INACTIVE"] as const;

export default function DeliveryZonesScreen() {
  const theme = useTheme(); const { horizontalPadding } = useResponsiveLayout(); const router = useRouter();
  const [status, setStatus] = useState<(typeof statuses)[number]>();
  const query = useInfiniteQuery({ queryKey: queryKeys.deliveryZones(status), queryFn: ({ pageParam, signal }) => staffApi.deliveryZones(status, pageParam, signal), initialPageParam: undefined as string | undefined, getNextPageParam: (last) => last.next_cursor ?? undefined });
  const items = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);
  return <FlatList style={{ backgroundColor: theme.colors.background }} data={items} keyExtractor={(item) => item.id} contentContainerStyle={[styles.page, { paddingHorizontal: horizontalPadding }]}
    ListHeaderComponent={<View style={styles.header}><SectionHeader title="Delivery Zones" action={<Button label="Add zone" icon="add-outline" onPress={() => router.push("/(protected)/delivery-zones/new" as never)} />} /><AppText color="secondary">Active tenant-owned boundaries are the delivery authority.</AppText><View style={styles.filters}>{statuses.map((value) => <FilterChip key={value ?? "ALL"} label={value ?? "All"} selected={value === status} onPress={() => setStatus(value)} />)}</View></View>}
    renderItem={({ item }) => <Card variant="interactive" accessibilityLabel={`${item.name}, ${item.status}`} onPress={() => router.push(`/(protected)/delivery-zones/${item.id}` as never)}><Inline between><AppText variant="titleSmall" weight="bold">{item.name}</AppText><StatusBadge label={item.status} tone={item.status === "ACTIVE" ? "success" : item.status === "DRAFT" ? "warning" : "neutral"} /></Inline><KeyValueRow label="Priority" value={String(item.priority)} /><KeyValueRow label="Version" value={String(item.version)} /></Card>}
    ItemSeparatorComponent={() => <View style={{ height: spacing[2] }} />}
    ListEmptyComponent={query.isPending ? <Loading label="Loading delivery zones" /> : query.isError ? <ErrorState title="Delivery zones unavailable" action={<Button label="Retry" onPress={() => void query.refetch()} />} /> : <StateMessage title={status ? `No ${status.toLowerCase()} zones` : "No delivery zones"} message="Create a bounded coverage boundary to begin serviceability checks." />}
    refreshing={query.isRefetching && !query.isFetchingNextPage} onRefresh={() => void query.refetch()} onEndReached={() => { if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage(); }} />;
}

const styles = StyleSheet.create({ page: { width: "100%", maxWidth: 1440, alignSelf: "center", paddingVertical: spacing[4], paddingBottom: spacing[8] }, header: { gap: spacing[3], marginBottom: spacing[4] }, filters: { flexDirection: "row", flexWrap: "wrap", gap: spacing[2] } });
