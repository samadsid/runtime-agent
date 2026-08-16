import * as Application from "expo-application";
import { Alert, ScrollView, StyleSheet, Text } from "react-native";

import { useAuth } from "@/auth/auth-context";
import { Button, Card, Screen, dsStyles } from "@/components/design-system";
import { spacing, useTheme } from "@/components/design-system/theme";

export default function AccountScreen() {
  const auth = useAuth(); const theme = useTheme(); const identity = auth.identity;
  return <Screen><ScrollView contentContainerStyle={styles.page}><Text style={[dsStyles.title, { color: theme.text }]}>Account</Text>
    <Card><Text style={[dsStyles.heading, { color: theme.text }]}>{identity?.display_name}</Text><Text style={{ color: theme.muted }}>{identity?.active_membership.role.replaceAll("_", " ")}</Text><Text style={{ color: theme.muted }}>Tenant {identity?.active_membership.tenant_id}</Text></Card>
    <Card><Text style={{ color: theme.text }}>Version {Application.nativeApplicationVersion ?? "development"} ({Application.nativeBuildVersion ?? "local"})</Text></Card>
    <Button variant="destructive" label="Log out" onPress={() => Alert.alert("Log out?", "Protected order data will be cleared from this device.", [{ text: "Stay", style: "cancel" }, { text: "Log out", style: "destructive", onPress: () => void auth.logout() }])} />
  </ScrollView></Screen>;
}
const styles = StyleSheet.create({ page: { padding: spacing.md, gap: spacing.md } });
