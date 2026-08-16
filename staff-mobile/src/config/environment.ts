import { z } from "zod";

const environmentSchema = z.object({
  apiBaseUrl: z.string().url(),
  appEnvironment: z.enum(["development", "staging", "production"]),
  requestTimeoutMs: z.coerce.number().int().min(1000).max(60000),
});

export type Environment = z.infer<typeof environmentSchema>;

export function readEnvironment(source: Record<string, string | undefined> = process.env): Environment {
  const result = environmentSchema.safeParse({
    apiBaseUrl: source.EXPO_PUBLIC_API_BASE_URL,
    appEnvironment: source.EXPO_PUBLIC_APP_ENV,
    requestTimeoutMs: source.EXPO_PUBLIC_REQUEST_TIMEOUT_MS ?? "15000",
  });
  if (!result.success) {
    throw new Error("The mobile application environment is not configured safely.");
  }
  const normalized = {
    ...result.data,
    apiBaseUrl: result.data.apiBaseUrl.replace(/\/$/, ""),
  };
  if (normalized.appEnvironment !== "development" && !normalized.apiBaseUrl.startsWith("https://")) {
    throw new Error("HTTPS is required outside development.");
  }
  if (normalized.appEnvironment === "production" && /localhost|127\.0\.0\.1/.test(normalized.apiBaseUrl)) {
    throw new Error("Production cannot use a local API URL.");
  }
  return normalized;
}
