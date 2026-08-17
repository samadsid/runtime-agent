import * as Application from "expo-application";
import { useState } from "react";
import { StyleSheet } from "react-native";

import { useAuth } from "@/auth/auth-context";
import { AppText, Button, Card, Confirmation, KeyValueRow, ResponsiveContainer, Screen, SectionHeader, spacing } from "@/design-system";

export default function AccountScreen() {
  const auth = useAuth(); const identity = auth.identity; const [confirming, setConfirming] = useState(false);
  return <Screen><ResponsiveContainer scroll contentStyle={styles.page}><SectionHeader title="Account" />
    <Card><AppText variant="titleMedium" weight="bold">{identity?.display_name}</AppText><AppText color="secondary">{identity?.active_membership.role.replaceAll("_", " ")}</AppText><KeyValueRow label="Tenant" value={identity?.active_membership.tenant_id ?? "—"} /></Card>
    <Card variant="outlined"><KeyValueRow label="App version" value={`${Application.nativeApplicationVersion ?? "development"} (${Application.nativeBuildVersion ?? "local"})`} /><KeyValueRow label="Appearance" value="System setting" /></Card>
    <Button variant="secondary" icon="log-out-outline" label="Log out" onPress={() => setConfirming(true)} />
  </ResponsiveContainer><Confirmation visible={confirming} title="Log out?" message="Protected order data will be cleared from this device." confirmLabel="Log out" onConfirm={() => void auth.logout()} onCancel={() => setConfirming(false)} /></Screen>;
}
const styles = StyleSheet.create({ page: { gap: spacing[4], paddingBottom: spacing[8] } });
