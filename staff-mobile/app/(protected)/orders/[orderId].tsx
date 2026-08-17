import { useMutation, useQuery } from "@tanstack/react-query";
import * as Crypto from "expo-crypto";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { AccessibilityInfo, RefreshControl, ScrollView, StyleSheet, View } from "react-native";

import type { PermittedOrderAction } from "@/api/contracts";
import { StaffApiError } from "@/api/errors";
import { staffApi } from "@/app-services";
import { useAuth } from "@/auth/auth-context";
import { mutationAttempts } from "@/auth/mutation-attempts";
import { AppText, Banner, Button, Card, Confirmation, ErrorState, Inline, KeyValueRow, Loading, Screen, SectionHeader, StatusBadge, TextField, spacing, useResponsiveLayout, useTheme } from "@/design-system";
import { formatDateTime, formatMoney, statusActionLabel } from "@/features/orders/presentation";
import { presentOrderStatus } from "@/features/presentation/status";
import { recordEvent } from "@/observability/events";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";

export default function OrderDetailsScreen() {
  const { orderId = "" } = useLocalSearchParams<{ orderId: string }>(); const theme = useTheme(); const { horizontalPadding, expanded } = useResponsiveLayout(); const auth = useAuth();
  const [pendingAction, setPendingAction] = useState<PermittedOrderAction | null>(null); const [reason, setReason] = useState(""); const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const query = useQuery({ queryKey: queryKeys.order(orderId), queryFn: ({ signal }) => staffApi.order(orderId, signal), gcTime: 0 });
  const mutation = useMutation({ mutationFn: staffApi.transition, onSuccess: async (response) => {
    mutationAttempts.clear(); setErrorMessage(null); setPendingAction(null); setReason("");
    await Promise.all([queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }), queryClient.invalidateQueries({ queryKey: ["staff", "orders"] }), queryClient.invalidateQueries({ queryKey: queryKeys.order(orderId) })]);
    recordEvent("order_transition_succeeded", { status: response.status }); AccessibilityInfo.announceForAccessibility(`Order status is now ${response.status.replaceAll("_", " ")}.`);
  }, onError: async (error) => {
    const apiError = error instanceof StaffApiError ? error : null; recordEvent("order_transition_failed_category", { category: apiError?.code ?? "unexpected" });
    if (apiError?.ambiguous) { mutationAttempts.markAmbiguous(); setErrorMessage("The result is unknown. Retry this same action safely, or refresh the order first."); return; }
    setPendingAction(null);
    if (apiError?.code === "stale_order_version" || apiError?.code === "invalid_transition") { mutationAttempts.clear(); recordEvent("stale_order_detected"); await query.refetch(); setErrorMessage("Another staff member changed this order. Review the latest status before choosing another action."); return; }
    if (apiError?.code === "idempotency_key_conflict") { mutationAttempts.clear(); await query.refetch(); setErrorMessage("This request could not be retried safely. Review the latest order and start again."); return; }
    if (apiError?.code === "staff_access_denied") { await auth.refreshIdentity(); await query.refetch(); setErrorMessage("You no longer have permission for that action."); return; }
    setErrorMessage(apiError?.message ?? "The action could not be completed.");
  }});
  if (query.isPending) return <Screen><Loading label="Loading order details" /></Screen>;
  if (query.isError || !query.data) return <Screen><ErrorState title="Order unavailable" message="It may have changed or you may not have access." action={<Button label="Retry" onPress={() => void query.refetch()} />} /></Screen>;
  const order = query.data; const status = presentOrderStatus(order.status);
  const visibleActions = order.permitted_actions.filter((action) => action.target_status !== "CANCELLED" || auth.identity?.active_membership.role === "ADMIN");
  const execute = (action: PermittedOrderAction, actionReason: string | null = null) => { const input = { orderId, targetStatus: action.target_status, reason: actionReason, version: order.version }; const existing = mutationAttempts.getMatching(input); const attempt = existing ?? { ...input, idempotencyKey: Crypto.randomUUID(), ambiguous: false }; mutationAttempts.set(attempt); mutation.mutate(attempt); };
  const retry = mutationAttempts.getMatching({ orderId, targetStatus: mutation.variables?.targetStatus ?? order.status, reason: mutation.variables?.reason ?? null, version: mutation.variables?.version ?? order.version });
  const confirmPending = () => { if (!pendingAction) return; execute(pendingAction, pendingAction.requires_reason ? reason.trim() : null); };
  const actionPanel = <View style={styles.actionPanel}>{visibleActions.length ? <SectionHeader title="Available actions" /> : null}{visibleActions.filter((action) => action.target_status !== "CANCELLED").map((action) => <Button key={action.target_status} label={statusActionLabel(action.target_status)} disabled={mutation.isPending} onPress={() => setPendingAction(action)} />)}{visibleActions.filter((action) => action.target_status === "CANCELLED").map((action) => <Button key={action.target_status} variant="danger" label={statusActionLabel(action.target_status)} disabled={mutation.isPending} onPress={() => setPendingAction(action)} />)}</View>;
  return <Screen><ScrollView refreshControl={<RefreshControl colors={[theme.colors.brand]} refreshing={query.isRefetching} onRefresh={() => { mutationAttempts.clear(); setErrorMessage(null); void query.refetch(); }} />} contentContainerStyle={[styles.page, { paddingHorizontal: horizontalPadding }]}>
    <Inline between style={styles.top}><View style={styles.flex}><AppText variant="titleLarge" weight="bold">Order {order.order_reference}</AppText><AppText color="secondary">Updated {formatDateTime(order.updated_at)}</AppText></View><StatusBadge {...status} /></Inline>
    {errorMessage ? <Banner tone="danger" message={errorMessage} action={retry?.ambiguous ? <Button variant="secondary" label="Retry same action" disabled={mutation.isPending} onPress={() => mutation.mutate(retry)} /> : undefined} /> : null}
    <View style={expanded ? styles.columns : styles.stack}><View style={[styles.stack, styles.flex]}>
      <Card><SectionHeader title="Order summary" /><KeyValueRow label="Total" value={formatMoney(order.total, order.currency)} primary /><KeyValueRow label="Payment" value={`${order.payment_method.replaceAll("_", " ")}${order.payment_status ? ` · ${order.payment_status.replaceAll("_", " ")}` : ""}`} /></Card>
      <Card><SectionHeader title="Delivery" /><AppText variant="bodyLarge" weight="semibold">{order.customer_name}</AppText><AppText selectable>{order.phone_number}</AppText><AppText selectable>{order.delivery_address}</AppText></Card>
      <View style={styles.stack}><SectionHeader title="Items" />{order.items.map((item, index) => <Card key={`${item.product_name}-${index}`} variant="outlined"><AppText variant="titleSmall" weight="bold">{item.product_name}</AppText><KeyValueRow label={`${item.quantity} ${item.unit} × ${formatMoney(item.unit_price, item.currency)}`} value={formatMoney(item.line_total, item.currency)} /></Card>)}</View>
      <View style={styles.stack}><SectionHeader title="Status timeline" />{order.timeline.map((entry, index) => { const entryStatus = presentOrderStatus(entry.to_status); return <View key={`${entry.created_at}-${index}`} style={styles.timelineEntry}><View style={[styles.dot, { backgroundColor: theme.colors[entryStatus.tone === "neutral" ? "textSecondary" : entryStatus.tone] }]} /><View style={styles.flex}><AppText weight="bold">{entryStatus.label}</AppText><AppText color="secondary">{formatDateTime(entry.created_at)} · {entry.actor_type}</AppText>{entry.reason ? <AppText>{entry.reason}</AppText> : null}</View></View>; })}</View>
    </View>{expanded ? <View style={styles.side}>{actionPanel}</View> : null}</View>{!expanded ? actionPanel : null}
  </ScrollView><Confirmation visible={Boolean(pendingAction)} title={pendingAction?.target_status === "CANCELLED" ? `Cancel ${order.order_reference}?` : `${pendingAction ? statusActionLabel(pendingAction.target_status) : "Update order"}?`} message={pendingAction?.target_status === "CANCELLED" ? "Cancellation may release reserved inventory and notify the customer." : `Apply this action to ${order.order_reference}.`} confirmLabel={pendingAction?.target_status === "CANCELLED" ? "Cancel order" : "Confirm update"} danger={pendingAction?.target_status === "CANCELLED"} busy={mutation.isPending} onConfirm={confirmPending} onCancel={() => { if (!mutation.isPending) { setPendingAction(null); setReason(""); } }}>{pendingAction?.requires_reason ? <TextField label="Cancellation reason" required value={reason} onChangeText={setReason} multiline error={!reason.trim() ? "A reason is required." : undefined} /> : null}</Confirmation></Screen>;
}
const styles = StyleSheet.create({ page: { width: "100%", maxWidth: 1440, alignSelf: "center", paddingVertical: spacing[4], paddingBottom: spacing[10], gap: spacing[5] }, top: { alignItems: "flex-start" }, flex: { flex: 1 }, stack: { gap: spacing[4] }, columns: { flexDirection: "row", alignItems: "flex-start", gap: spacing[6] }, side: { width: 320 }, actionPanel: { gap: spacing[3] }, timelineEntry: { flexDirection: "row", gap: spacing[3], paddingLeft: spacing[2] }, dot: { width: 12, height: 12, borderRadius: 6, marginTop: spacing[1] } });
