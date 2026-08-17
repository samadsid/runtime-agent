import { QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider, useAuth } from "@/auth/auth-context";
import { configurationError } from "@/app-services";
import { OfflineBanner } from "@/components/offline-banner";
import { Button, ErrorState, Loading, Screen, ThemeProvider, useTheme } from "@/design-system";
import { queryClient } from "@/query/query-client";

function NavigationGate() {
  const auth = useAuth();
  const segments = useSegments();
  const router = useRouter();
  useEffect(() => {
    if (auth.state === "restoring" || auth.state === "connection_error") return;
    const protectedRoute = segments[0] === "(protected)";
    if (auth.state === "authenticated" && !protectedRoute) router.replace("/(protected)/dashboard");
    if (auth.state === "anonymous" && protectedRoute) { router.dismissAll(); router.replace("/(public)/login"); }
  }, [auth.state, router, segments]);
  if (auth.state === "restoring") return <Screen><Loading label="Restoring secure session" /></Screen>;
  if (auth.state === "connection_error") return <Screen><ErrorState title="Cannot verify your session" message="Connect to the staff service and retry. An unvalidated token cannot open protected data." action={<Button label="Retry" onPress={() => void auth.retryRestore()} />} /></Screen>;
  return <><OfflineBanner /><Stack screenOptions={{ headerShown: false }} /></>;
}

function ThemedApplication() {
  const theme = useTheme();
  if (configurationError) return <Screen><ErrorState title="Application not configured" message="Set a valid staff API URL and application environment, then restart the app." /></Screen>;
  return <QueryClientProvider client={queryClient}><AuthProvider><StatusBar style={theme.mode === "dark" ? "light" : "dark"} /><NavigationGate /></AuthProvider></QueryClientProvider>;
}

export default function RootLayout() {
  return <SafeAreaProvider><ThemeProvider><ThemedApplication /></ThemeProvider></SafeAreaProvider>;
}
