import * as Application from "expo-application";
import { z, type ZodType } from "zod";

import type { Environment } from "@/config/environment";
import { apiErrorSchema } from "./contracts";
import { contractError, StaffApiError, type StaffApiErrorCode } from "./errors";

type RequestOptions<T> = {
  method?: "GET" | "POST" | "PATCH";
  authenticated?: boolean;
  body?: unknown;
  headers?: Record<string, string>;
  schema: ZodType<T>;
  signal?: AbortSignal;
  mutation?: boolean;
};

export class StaffApiClient {
  private token: string | null = null;
  private onInvalidToken: (() => void) | null = null;

  constructor(private readonly environment: Environment) {}

  setToken(token: string | null): void { this.token = token; }
  setInvalidTokenHandler(handler: (() => void) | null): void { this.onInvalidToken = handler; }

  async request<T>(path: string, options: RequestOptions<T>): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort("timeout"), this.environment.requestTimeoutMs);
    const abort = () => controller.abort("cancelled");
    options.signal?.addEventListener("abort", abort, { once: true });
    const headers: Record<string, string> = {
      Accept: "application/json",
      "X-App-Version": Application.nativeApplicationVersion ?? "development",
      ...options.headers,
    };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (options.authenticated) {
      if (!this.token) throw new StaffApiError(401, "invalid_access_token", "Please log in again.");
      headers.Authorization = `Bearer ${this.token}`;
    }
    try {
      const response = await fetch(`${this.environment.apiBaseUrl}${path}`, {
        method: options.method ?? "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
      const json: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const parsed = apiErrorSchema.safeParse(json);
        const error = parsed.success ? parsed.data.error : null;
        if (response.status === 401 && error?.code === "invalid_access_token") this.onInvalidToken?.();
        throw new StaffApiError(
          response.status,
          (error?.code as StaffApiErrorCode | undefined) ?? "unexpected_response",
          error?.message ?? "The request could not be completed.",
          error?.request_id,
        );
      }
      const parsed = options.schema.safeParse(json);
      if (!parsed.success) throw contractError(parsed.error);
      return parsed.data;
    } catch (error) {
      if (error instanceof StaffApiError) throw error;
      if (controller.signal.aborted && controller.signal.reason === "timeout") {
        throw new StaffApiError(null, "timeout", "The request timed out.", undefined, Boolean(options.mutation));
      }
      if (controller.signal.aborted) throw error;
      throw new StaffApiError(null, "network_error", "The server could not be reached.", undefined, Boolean(options.mutation));
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", abort);
    }
  }
}
