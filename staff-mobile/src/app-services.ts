import { StaffApiClient } from "@/api/client";
import { createStaffApi } from "@/api/staff-api";
import { readEnvironment, type Environment } from "@/config/environment";

export let configurationError: Error | null = null;
let resolvedEnvironment: Environment;
try {
  resolvedEnvironment = readEnvironment();
} catch (error) {
  configurationError = error instanceof Error ? error : new Error("Invalid application configuration.");
  resolvedEnvironment = { apiBaseUrl: "http://127.0.0.1:1", appEnvironment: "development", requestTimeoutMs: 1000 };
}
export const environment = resolvedEnvironment;
export const apiClient = new StaffApiClient(environment);
export const staffApi = createStaffApi(apiClient);
