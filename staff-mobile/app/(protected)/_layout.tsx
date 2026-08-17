import { Tabs } from "expo-router";

import { useAuth } from "@/auth/auth-context";
import { AppIcon, useResponsiveLayout, useTheme } from "@/design-system";

export default function ProtectedLayout() {
  const theme = useTheme();
  const { compact } = useResponsiveLayout();
  const { identity } = useAuth();
  const admin = identity?.active_membership.role === "ADMIN";
  return <Tabs screenOptions={{ headerShown: false, tabBarPosition: compact ? "bottom" : "left", tabBarActiveTintColor: theme.colors.brand, tabBarInactiveTintColor: theme.colors.textSecondary, tabBarLabelPosition: compact ? "below-icon" : "beside-icon", tabBarStyle: { backgroundColor: theme.colors.surface, borderColor: theme.colors.border, width: compact ? undefined : 216 }, tabBarItemStyle: { minHeight: 56 }, sceneStyle: { backgroundColor: theme.colors.background } }}>
    <Tabs.Screen name="dashboard" options={{ title: "Dashboard", tabBarIcon: () => <AppIcon name="grid-outline" color="brand" /> }} />
    <Tabs.Screen name="orders" options={{ title: "Orders", tabBarIcon: () => <AppIcon name="receipt-outline" color="brand" /> }} />
    <Tabs.Screen name="catalog" options={{ href: admin ? undefined : null, title: "Catalog", tabBarIcon: () => <AppIcon name="pricetags-outline" color="brand" /> }} />
    <Tabs.Screen name="inventory" options={{ href: admin ? undefined : null, title: "Inventory", tabBarIcon: () => <AppIcon name="cube-outline" color="brand" /> }} />
    <Tabs.Screen name="account" options={{ title: "Account", tabBarIcon: () => <AppIcon name="person-outline" color="brand" /> }} />
    <Tabs.Screen name="gallery" options={{ href: null }} />
  </Tabs>;
}
