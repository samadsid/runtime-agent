import { Stack } from "expo-router";
import { useTheme } from "@/design-system";

export default function OrdersLayout() {
  const theme = useTheme();
  return <Stack screenOptions={{ headerStyle: { backgroundColor: theme.colors.surface }, headerTintColor: theme.colors.textPrimary, contentStyle: { backgroundColor: theme.colors.background } }}>
    <Stack.Screen name="index" options={{ headerShown: false }} />
    <Stack.Screen name="[orderId]" options={{ title: "Order details" }} />
  </Stack>;
}
