import type { ConfigContext, ExpoConfig } from "expo/config";

const profiles = {
  development: {
    name: "AI Commerce Staff (Dev)",
    android: "com.commerceagent.staff.development",
    ios: "com.commerceagent.staff.development",
  },
  staging: {
    name: "AI Commerce Staff (Staging)",
    android: "com.commerceagent.staff.staging",
    ios: "com.commerceagent.staff.staging",
  },
  production: {
    name: "AI Commerce Staff",
    android: "com.commerceagent.staff",
    ios: "com.commerceagent.staff",
  },
} as const;

export default ({ config }: ConfigContext): ExpoConfig => {
  const environment = process.env.EXPO_PUBLIC_APP_ENV ?? "development";
  if (!(environment in profiles)) {
    throw new Error(`Unsupported EXPO_PUBLIC_APP_ENV: ${environment}`);
  }
  const profile = profiles[environment as keyof typeof profiles];
  return {
    ...config,
    name: profile.name,
    slug: "commerce-staff-mobile",
    scheme: "commerce-staff",
    version: "0.1.0",
    orientation: "portrait",
    userInterfaceStyle: "automatic",
    plugins: [
      "expo-router",
      "expo-secure-store",
      ["expo-build-properties", {
        android: { minSdkVersion: 24, usesCleartextTraffic: environment === "development" },
      }],
    ],
    experiments: { typedRoutes: true },
    android: {
      package: profile.android,
    },
    ios: { bundleIdentifier: profile.ios, supportsTablet: false },
  };
};
