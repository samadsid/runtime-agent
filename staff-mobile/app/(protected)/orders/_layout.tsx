import { Stack } from "expo-router";
import { useTheme } from "@/components/design-system/theme";

export default function OrdersLayout() {
  const theme = useTheme();
  return <Stack screenOptions={{ headerStyle: { backgroundColor: theme.surface }, headerTintColor: theme.text, contentStyle: { backgroundColor: theme.background } }}>
    <Stack.Screen name="index" options={{ headerShown: false }} />
    <Stack.Screen name="[orderId]" options={{ title: "Order details" }} />
  </Stack>;
}
