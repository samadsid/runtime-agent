import { Redirect } from "expo-router";
import { StyleSheet, View } from "react-native";

import { AppText, Banner, Button, Card, EmptyState, ErrorState, FilterChip, LoadingSkeleton, MetricCard, ResponsiveContainer, SectionHeader, StatusBadge, TextField, spacing } from "@/design-system";
import { presentOrderStatus } from "@/features/presentation/status";

export default function ComponentGallery() {
  if (process.env.EXPO_PUBLIC_APP_ENV === "production") return <Redirect href="/(protected)/dashboard" />;
  return <ResponsiveContainer scroll contentStyle={styles.page}><AppText variant="display" weight="bold">Component gallery</AppText><AppText color="secondary">Synthetic development data only.</AppText>
    <SectionHeader title="Actions" /><View style={styles.row}><Button label="Primary" onPress={() => undefined} /><Button variant="secondary" label="Secondary" onPress={() => undefined} /><Button variant="danger" label="Danger" onPress={() => undefined} /><Button label="Loading" loading onPress={() => undefined} /></View>
    <SectionHeader title="Fields and filters" /><TextField label="Product name" required value="Synthetic product" onChangeText={() => undefined} help="Persistent help text" /><TextField label="Quantity" value="" onChangeText={() => undefined} error="Enter a quantity." /><View style={styles.row}><FilterChip label="All" selected onPress={() => undefined} /><FilterChip label="Low stock" onPress={() => undefined} /></View>
    <SectionHeader title="Operational display" /><View style={styles.row}><StatusBadge {...presentOrderStatus("CONFIRMED")} /><StatusBadge {...presentOrderStatus("OUT_FOR_DELIVERY")} /><StatusBadge {...presentOrderStatus("CANCELLED")} /></View><MetricCard label="Confirmed" value={12} icon="checkmark-circle-outline" />
    <SectionHeader title="Feedback" /><Banner message="Displayed data may be stale." /><Banner tone="success" message="Synthetic update completed." /><Card><LoadingSkeleton rows={2} /></Card><EmptyState title="Nothing here" message="A contextual action can appear here." /><ErrorState title="Could not load" message="Safe synthetic error copy." />
  </ResponsiveContainer>;
}
const styles = StyleSheet.create({ page: { gap: spacing[4], paddingBottom: spacing[10] }, row: { flexDirection: "row", flexWrap: "wrap", gap: spacing[2] } });
