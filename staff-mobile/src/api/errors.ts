import { ZodError } from "zod";

export type StaffApiErrorCode =
  | "invalid_request" | "invalid_credentials" | "invalid_access_token"
  | "staff_access_denied" | "order_not_found" | "invalid_transition"
  | "stale_order_version" | "idempotency_key_conflict"
  | "cancellation_reason_required" | "rate_limit_exceeded"
  | "temporarily_unavailable" | "unexpected_response" | "timeout" | "network_error";

export class StaffApiError extends Error {
  constructor(
    public readonly status: number | null,
    public readonly code: StaffApiErrorCode,
    message: string,
    public readonly requestId?: string,
    public readonly ambiguous = false,
  ) { super(message); }
}

export function contractError(error: ZodError): StaffApiError {
  if (__DEV__) console.warn("Staff API contract mismatch", error.issues.map(({ path, code }) => ({ path, code })));
  return new StaffApiError(null, "unexpected_response", "The server response requires an app update.");
}
