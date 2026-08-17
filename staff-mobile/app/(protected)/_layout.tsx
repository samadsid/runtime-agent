import { Ionicons } from "@expo/vector-icons";
import { Tabs } from "expo-router";

import { useTheme } from "@/components/design-system/theme";
import { useAuth } from "@/auth/auth-context";

export default function ProtectedLayout() {
  const theme = useTheme();
  const { identity } = useAuth();
  const admin = identity?.active_membership.role === "ADMIN";
  return <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: theme.primary, tabBarInactiveTintColor: theme.muted, tabBarStyle: { backgroundColor: theme.surface, borderTopColor: theme.border } }}>
    <Tabs.Screen name="dashboard" options={{ title: "Dashboard", tabBarIcon: ({ color, size }) => <Ionicons name="grid-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="orders" options={{ title: "Orders", tabBarIcon: ({ color, size }) => <Ionicons name="receipt-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="catalog" options={{ href: admin ? undefined : null, title: "Catalog", tabBarIcon: ({ color, size }) => <Ionicons name="pricetags-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="inventory" options={{ href: admin ? undefined : null, title: "Inventory", tabBarIcon: ({ color, size }) => <Ionicons name="cube-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="account" options={{ title: "Account", tabBarIcon: ({ color, size }) => <Ionicons name="person-outline" color={color} size={size} /> }} />
  </Tabs>;
}
