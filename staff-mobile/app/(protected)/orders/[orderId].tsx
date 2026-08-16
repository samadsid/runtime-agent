import { useMutation, useQuery } from "@tanstack/react-query";
import * as Crypto from "expo-crypto";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { AccessibilityInfo, Alert, KeyboardAvoidingView, Modal, Platform, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import type { OrderStatus, PermittedOrderAction } from "@/api/contracts";
import { StaffApiError } from "@/api/errors";
import { staffApi } from "@/app-services";
import { useAuth } from "@/auth/auth-context";
import { mutationAttempts } from "@/auth/mutation-attempts";
import { Button, Card, Field, Loading, Screen, StateMessage, StatusBadge, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";
import { formatDateTime, formatMoney, statusActionLabel } from "@/features/orders/presentation";
import { recordEvent } from "@/observability/events";
import { queryClient } from "@/query/query-client";
import { queryKeys } from "@/query/query-keys";

export default function OrderDetailsScreen() {
  const { orderId = "" } = useLocalSearchParams<{ orderId: string }>(); const theme = useTheme(); const auth = useAuth();
  const [cancelOpen, setCancelOpen] = useState(false); const [reason, setReason] = useState(""); const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const query = useQuery({ queryKey: queryKeys.order(orderId), queryFn: ({ signal }) => staffApi.order(orderId, signal), gcTime: 0 });
  const mutation = useMutation({ mutationFn: staffApi.transition, onSuccess: async (response) => {
    mutationAttempts.clear(); setErrorMessage(null); setCancelOpen(false); setReason("");
    await Promise.all([queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }), queryClient.invalidateQueries({ queryKey: ["staff", "orders"] }), queryClient.invalidateQueries({ queryKey: queryKeys.order(orderId) })]);
    recordEvent("order_transition_succeeded", { status: response.status });
    AccessibilityInfo.announceForAccessibility(`Order status is now ${response.status.replaceAll("_", " ")}.`);
  }, onError: async (error) => {
    const apiError = error instanceof StaffApiError ? error : null;
    recordEvent("order_transition_failed_category", { category: apiError?.code ?? "unexpected" });
    if (apiError?.ambiguous) { mutationAttempts.markAmbiguous(); setErrorMessage("The result is unknown. Retry this same action safely, or refresh the order first."); return; }
    if (apiError?.code === "stale_order_version" || apiError?.code === "invalid_transition") {
      mutationAttempts.clear(); recordEvent("stale_order_detected"); await query.refetch();
      setErrorMessage("Another staff member changed this order. Review the latest status before choosing another action."); return;
    }
    if (apiError?.code === "idempotency_key_conflict") { mutationAttempts.clear(); await query.refetch(); setErrorMessage("This request could not be retried safely. Review the latest order and start again."); return; }
    if (apiError?.code === "staff_access_denied") { await auth.refreshIdentity(); await query.refetch(); setErrorMessage("You no longer have permission for that action."); return; }
    setErrorMessage(apiError?.message ?? "The action could not be completed.");
  }});
  if (query.isPending) return <Screen><Loading label="Loading order details" /></Screen>;
  if (query.isError || !query.data) return <Screen><StateMessage title="Order unavailable" message="It may have changed or you may not have access." action={<Button label="Retry" onPress={() => void query.refetch()} />} /></Screen>;
  const order = query.data;
  const visibleActions = order.permitted_actions.filter((action) =>
    action.target_status !== "CANCELLED" || auth.identity?.active_membership.role === "ADMIN"
  );
  const execute = (action: PermittedOrderAction, actionReason: string | null = null) => {
    const input = { orderId, targetStatus: action.target_status, reason: actionReason, version: order.version };
    const existing = mutationAttempts.getMatching(input);
    const attempt = existing ?? { ...input, idempotencyKey: Crypto.randomUUID(), ambiguous: false };
    mutationAttempts.set(attempt); mutation.mutate(attempt);
  };
  const confirm = (action: PermittedOrderAction) => {
    if (action.requires_reason) { setCancelOpen(true); return; }
    Alert.alert(`${statusActionLabel(action.target_status)}?`, `Apply this action to ${order.order_reference}?`, [{ text: "Back", style: "cancel" }, { text: "Confirm", onPress: () => execute(action) }]);
  };
  const retry = mutationAttempts.getMatching({ orderId, targetStatus: mutation.variables?.targetStatus ?? order.status, reason: mutation.variables?.reason ?? null, version: mutation.variables?.version ?? order.version });
  return <Screen><ScrollView refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => { mutationAttempts.clear(); setErrorMessage(null); void query.refetch(); }} />} contentContainerStyle={styles.page}>
    <View style={styles.between}><Text style={[dsStyles.heading, { color: theme.text, flex: 1 }]}>{order.order_reference}</Text><StatusBadge status={order.status} /></View>
    {errorMessage ? <Card><Text accessibilityRole="alert" style={{ color: theme.danger }}>{errorMessage}</Text>{retry?.ambiguous ? <Button label="Retry same action" disabled={mutation.isPending} onPress={() => mutation.mutate(retry)} /> : null}</Card> : null}
    <Card><Text style={[dsStyles.heading, { color: theme.text }]}>Delivery</Text><Text style={[dsStyles.body, { color: theme.text }]}>{order.customer_name}</Text><Text selectable style={[dsStyles.body, { color: theme.text }]}>{order.phone_number}</Text><Text selectable style={[dsStyles.body, { color: theme.text }]}>{order.delivery_address}</Text></Card>
    <Card><Text style={[dsStyles.heading, { color: theme.text }]}>Payment</Text><Text style={{ color: theme.text }}>{order.payment_method.replaceAll("_", " ")}{order.payment_status ? ` · ${order.payment_status.replaceAll("_", " ")}` : ""}</Text><Text style={[dsStyles.heading, { color: theme.text }]}>{formatMoney(order.total, order.currency)}</Text></Card>
    <Text style={[dsStyles.heading, { color: theme.text }]}>Items</Text>{order.items.map((item, index) => <Card key={`${item.product_name}-${index}`}><Text style={[dsStyles.heading, { color: theme.text }]}>{item.product_name}</Text><Text style={{ color: theme.muted }}>{item.quantity} {item.unit} × {formatMoney(item.unit_price, item.currency)}</Text><Text style={{ color: theme.text, fontWeight: "700" }}>{formatMoney(item.line_total, item.currency)}</Text></Card>)}
    <Text style={[dsStyles.heading, { color: theme.text }]}>Timeline</Text>{order.timeline.map((entry, index) => <Card key={`${entry.created_at}-${index}`}><Text style={{ color: theme.text, fontWeight: "700" }}>{entry.to_status.replaceAll("_", " ")}</Text><Text style={{ color: theme.muted }}>{formatDateTime(entry.created_at)} · {entry.actor_type}</Text>{entry.reason ? <Text style={{ color: theme.text }}>{entry.reason}</Text> : null}</Card>)}
    <Text style={{ color: theme.muted }}>Last updated {formatDateTime(order.updated_at)}</Text>
    {visibleActions.length ? <><Text style={[dsStyles.heading, { color: theme.text }]}>Available actions</Text>{visibleActions.map((action) => <Button key={action.target_status} variant={action.target_status === "CANCELLED" ? "destructive" : "primary"} label={statusActionLabel(action.target_status)} disabled={mutation.isPending} onPress={() => confirm(action)} />)}</> : null}
  </ScrollView>
  <Modal visible={cancelOpen} transparent animationType="slide" onRequestClose={() => setCancelOpen(false)}><KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.overlay}><View style={[styles.sheet, { backgroundColor: theme.surface }]}><Text style={[dsStyles.heading, { color: theme.text }]}>Cancel {order.order_reference}?</Text><Text style={{ color: theme.muted }}>Cancellation may release reserved inventory and notify the customer.</Text><Field label="Cancellation reason" value={reason} onChangeText={setReason} multiline error={!reason.trim() ? "A reason is required." : undefined} /><Button variant="destructive" label={mutation.isPending ? "Cancelling…" : "Cancel order"} disabled={!reason.trim() || mutation.isPending} onPress={() => { const action = visibleActions.find((value) => value.target_status === "CANCELLED"); if (action) execute(action, reason.trim()); }} /><Button variant="secondary" label="Back" disabled={mutation.isPending} onPress={() => setCancelOpen(false)} /></View></KeyboardAvoidingView></Modal>
  </Screen>;
}
const styles = StyleSheet.create({ page: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xl }, between: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm }, overlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", justifyContent: "flex-end" }, sheet: { padding: spacing.lg, gap: spacing.md, borderTopLeftRadius: 20, borderTopRightRadius: 20 } });
